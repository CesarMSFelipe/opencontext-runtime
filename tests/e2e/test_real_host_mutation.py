"""Real MCP process-boundary mutation loop (real-host-dod-convergence REQ-3).

``tests/core/test_mcp_agent_execute.py`` already proves the agent_execute →
session_apply contract in-process and over stdin. This test closes the last
link a real host actually crosses: it spawns ``opencontext mcp --workflow-tools``
as a **separate process** and drives the exact JSON-RPC sequence a non-sampling
host (codex / claude / opencode) issues after it connects:

    initialize -> tools/call opencontext_run  (=> status: agent_execute)
      -> host applies the edits itself -> tools/call opencontext_session_apply
      -> run completes with a receipt and the fixture test passes

No provider credentials or network are involved.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIRS = (
    _REPO_ROOT / "packages" / "opencontext_core",
    _REPO_ROOT / "packages" / "opencontext_cli",
)


def _env(home: Path) -> dict[str, str]:
    entries = [
        str(Path(raw).resolve())
        for raw in os.environ.get("PYTHONPATH", "").split(os.pathsep)
        if raw
    ]
    for pkg in _PACKAGE_DIRS:
        if str(pkg) not in entries:
            entries.append(str(pkg))
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    env["PYTHONPATH"] = os.pathsep.join(entries)
    env["OPENCONTEXT_STORAGE_MODE"] = "local"
    return env


def _rpc(id_: Any, method: str, params: dict[str, Any] | None = None) -> str:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if id_ is not None:
        msg["id"] = id_
    return json.dumps(msg)


def _send(proc: subprocess.Popen[str], line: str) -> None:
    assert proc.stdin is not None
    proc.stdin.write(line + "\n")
    proc.stdin.flush()


def _read_response(
    proc: subprocess.Popen[str], want_id: Any, timeout: float = 60.0
) -> dict[str, Any]:
    """Read stdout JSON-RPC lines until the response with ``want_id`` arrives."""
    result: dict[str, list[dict[str, Any]]] = {"msgs": []}

    def _reader() -> None:
        assert proc.stdout is not None
        for raw in proc.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            result["msgs"].append(msg)
            if msg.get("id") == want_id:
                return

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    t.join(timeout)
    for msg in result["msgs"]:
        if msg.get("id") == want_id:
            return msg
    raise AssertionError(
        f"no JSON-RPC response with id={want_id} within {timeout}s; got {result['msgs']}"
    )


def _payload(message: dict[str, Any]) -> dict[str, Any]:
    return dict(message["result"]["structuredContent"]["data"])


def test_real_mcp_subprocess_agent_execute_then_apply_completes(tmp_path: Path) -> None:
    if shutil.which("opencontext") is None:
        pytest.skip("opencontext CLI not on PATH in this test environment")

    home = tmp_path / "home"
    work = tmp_path / "proj"
    home.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    (work / "buggy_add.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (work / "test_buggy_add.py").write_text(
        "from buggy_add import add\n\n\ndef test_add() -> None:\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        ["opencontext", "mcp", "--workflow-tools"],
        cwd=str(work),
        env=_env(home),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    try:
        _send(proc, _rpc(1, "initialize", {"capabilities": {}}))
        assert _read_response(proc, 1)["result"]["serverInfo"]["name"] == "opencontext-mcp"
        _send(proc, _rpc(None, "notifications/initialized"))

        # Non-sampling host asks OC to fix the failing test -> agent_execute handoff.
        _send(
            proc,
            _rpc(
                2,
                "tools/call",
                {
                    "name": "opencontext_run",
                    "arguments": {
                        "task": "Fix failing test",
                        "workflow": "oc-flow",
                        "root": str(work),
                    },
                },
            ),
        )
        handoff = _payload(_read_response(proc, 2))
        assert handoff["status"] == "agent_execute", handoff
        follow_up = handoff["follow_up"]
        assert follow_up["tool"] == "opencontext_session_apply"

        # The host makes the edit itself, then calls the follow-up exactly as told.
        (work / "buggy_add.py").write_text(
            "def add(a, b):\n    # host-executed fix\n    return a + b\n", encoding="utf-8"
        )
        args = dict(follow_up["arguments"])
        args["payload"] = dict(args["payload"])
        args["payload"]["changed_files"] = ["buggy_add.py"]
        args["payload"]["test_command"] = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "test_buggy_add.py",
        ]
        _send(proc, _rpc(3, "tools/call", {"name": "opencontext_session_apply", "arguments": args}))

        result = _payload(_read_response(proc, 3, timeout=120))
        assert result["applied"] is True, result
        assert result["status"] == "completed", result
        assert result["changed_files"] == ["buggy_add.py"]
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
