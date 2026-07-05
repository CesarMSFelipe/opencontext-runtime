"""Agent-execute handoff: MCP clients WITHOUT sampling get a working flow.

Clients that support MCP sampling (the ``sampling`` capability) already drive
OC Flow / SDD with their own selected model. Clients that do NOT (notably
Claude Code and Codex) used to dead-end in ``status: needs_executor`` when no
provider was configured. These tests pin the replacement contract:

* profile (a) — a client that declares ``sampling`` at initialize reaches the
  sampling path over the real stdio protocol and the run completes;
* profile (b) — a client that declares NO sampling gets a structured
  ``status: agent_execute`` handoff quickly (no sampling round-trip, no bare
  ``needs_executor``), and the follow-up ``opencontext_session_apply`` call
  with ``kind="agent_edits"`` completes the run with receipts.
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path
from typing import Any, ClassVar

import pytest

from opencontext_core.llm.sampling_gateway import register_host_sampler
from opencontext_core.mcp_stdio import MCPServer
from opencontext_core.oc_flow import cli as oc_flow_cli
from opencontext_core.paths import StorageMode, resolve_workspace_path
from opencontext_core.providers.detect import DetectedProvider
from opencontext_core.tools.policy import ToolPermissionPolicy

_VALID_EDIT_JSON = (
    '[{"path":"buggy_add.py","operation":"replace_range","start_line":2,"end_line":2,'
    '"content":"    return a + b","reason":"fix the operator",'
    '"requirement_refs":["add returns the sum"]}]'
)

# NOTE: deliberately a different byte size than the buggy version — a same-size
# rewrite within the same second would let a nested pytest reuse the stale
# __pycache__ bytecode compiled from the buggy source (mtime is whole seconds).
_FIXED_ADD = "def add(a, b):\n    # agent-executed fix\n    return a + b\n"


@pytest.fixture(autouse=True)
def _clear_sampler():
    register_host_sampler(None)
    yield
    register_host_sampler(None)


def _pin_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate from ambient API keys / local model servers."""
    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(name="mock", api_key="", model="mock", source="fallback"),
    )


def _server(tmp_path: Path) -> MCPServer:
    s = MCPServer(db_path=tmp_path / "kg.db")
    s.policy = ToolPermissionPolicy(allowed_tools=set(s.tools.keys()))
    return s


def _write_buggy_project(work: Path) -> None:
    """A minimal mutation target with NO provider config (zero-config project)."""
    work.mkdir(parents=True, exist_ok=True)
    (work / "buggy_add.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")


def _rpc(id_: Any, method: str, params: dict[str, Any] | None = None) -> str:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if id_ is not None:
        msg["id"] = id_
    return json.dumps(msg)


def _responses(raw: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _tool_payload(message: dict[str, Any]) -> dict[str, Any]:
    """Unwrap a tools/call JSON-RPC response into the tool's domain payload.

    ``structuredContent`` is the :class:`ToolResultEnvelope` (tool/status/data);
    the run/handoff payload lives under its ``data`` key.
    """
    return dict(message["result"]["structuredContent"]["data"])


def _flow_run_dir(root: Path, session_id: str, run_id: str) -> Path:
    return (
        resolve_workspace_path(root, StorageMode.local) / "sessions" / session_id / "runs" / run_id
    )


# --------------------------------------------------------------------------- #
# Profile (a): client WITH sampling — protocol-level, run completes.
# --------------------------------------------------------------------------- #


def test_sampling_client_protocol_run_reaches_sampling_and_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _pin_mock(monkeypatch)
    work = tmp_path / "proj"
    _write_buggy_project(work)
    server = _server(tmp_path)

    sampling_reply = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "oc-sampling-1",
            "result": {"content": {"type": "text", "text": _VALID_EDIT_JSON}},
        }
    )
    script = "\n".join(
        [
            _rpc(1, "initialize", {"capabilities": {"sampling": {}}}),
            _rpc(None, "notifications/initialized"),
            _rpc(
                2,
                "tools/call",
                {
                    "name": "opencontext_run",
                    "arguments": {
                        "task": "Fix add: it must return the sum",
                        "workflow": "oc-flow",
                        "root": str(work),
                    },
                },
            ),
            sampling_reply,
        ]
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(script + "\n"))

    server.run()

    out = _responses(capsys.readouterr().out)
    init = next(m for m in out if m.get("id") == 1)
    assert "sampling" in init["result"]["capabilities"]
    # The server actually asked the client's model to do the mutation.
    assert any(m.get("method") == "sampling/createMessage" for m in out)
    payload = _tool_payload(next(m for m in out if m.get("id") == 2))
    assert payload["status"] == "completed"
    assert payload["host_model_used"] is True
    assert (work / "buggy_add.py").read_text(encoding="utf-8") == (
        "def add(a, b):\n    return a + b\n"
    )
    server.close()


# --------------------------------------------------------------------------- #
# Profile (b): client WITHOUT sampling — agent_execute handoff + follow-up.
# --------------------------------------------------------------------------- #


def test_non_sampling_client_gets_agent_execute_handoff_fast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _pin_mock(monkeypatch)
    work = tmp_path / "proj"
    _write_buggy_project(work)
    server = _server(tmp_path)

    script = "\n".join(
        [
            _rpc(1, "initialize", {"capabilities": {}}),
            _rpc(None, "notifications/initialized"),
            _rpc(
                2,
                "tools/call",
                {
                    "name": "opencontext_run",
                    "arguments": {
                        "task": "Fix add: it must return the sum",
                        "workflow": "oc-flow",
                        "root": str(work),
                    },
                },
            ),
        ]
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(script + "\n"))

    start = time.monotonic()
    server.run()
    elapsed = time.monotonic() - start

    out = _responses(capsys.readouterr().out)
    # No sampling round-trip may ever be attempted against this client.
    assert not any(m.get("method") == "sampling/createMessage" for m in out)
    # And no 60s sampling-timeout stall: the handoff returns promptly.
    assert elapsed < 30

    payload = _tool_payload(next(m for m in out if m.get("id") == 2))
    assert payload["status"] == "agent_execute"
    assert payload["status"] != "needs_executor"
    # The handoff is actionable: contract + context + ordered instructions +
    # an exact follow-up tool call.
    contract = payload["task_contract"]
    assert contract and contract["acceptance_criteria"]
    assert isinstance(payload["context"]["items"], list)
    assert payload["instructions"] and len(payload["instructions"]) >= 3
    follow_up = payload["follow_up"]
    assert follow_up["tool"] == "opencontext_session_apply"
    assert follow_up["arguments"]["kind"] == "agent_edits"
    assert follow_up["arguments"]["session_id"].startswith("sess-")
    assert payload["session_id"] == follow_up["arguments"]["session_id"]
    # The OC Flow run stays resumable for the follow-up to complete.
    flow = payload["oc_flow_run"]
    state_path = _flow_run_dir(work, flow["session_id"], flow["run_id"]) / "state.json"
    assert state_path.is_file()
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == "needs_executor"
    server.close()


def test_agent_edits_follow_up_completes_the_flow_run_with_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_mock(monkeypatch)
    work = tmp_path / "proj"
    _write_buggy_project(work)
    server = _server(tmp_path)
    server._handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}}
    )

    run_out = server._call_tool(
        "opencontext_run",
        {"task": "Fix add: it must return the sum", "workflow": "oc-flow", "root": str(work)},
    )
    handoff = run_out["data"]
    assert handoff["status"] == "agent_execute"
    flow = handoff["oc_flow_run"]

    # The client agent makes the edit ITSELF (its own tools), as instructed...
    (work / "buggy_add.py").write_text(_FIXED_ADD, encoding="utf-8")

    # ...then calls the follow-up tool exactly as the handoff says.
    args = dict(handoff["follow_up"]["arguments"])
    args["payload"] = dict(args["payload"])
    args["payload"]["changed_files"] = ["buggy_add.py"]
    apply_out = server._call_tool("opencontext_session_apply", args)

    assert apply_out["status"] == "passed", apply_out
    result = apply_out["data"]
    assert result["applied"] is True
    assert result["status"] == "completed"
    assert result["changed_files"] == ["buggy_add.py"]

    # The evidence spine is persisted: state flipped + inspection + receipts.
    run_dir = _flow_run_dir(work, flow["session_id"], flow["run_id"])
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "completed"
    assert state["changed_files"] == ["buggy_add.py"]
    assert state["executed_by"] == "host-agent"
    artifacts = run_dir / "artifacts" / "oc-flow"
    report = json.loads((artifacts / "inspection-report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "passed"
    receipts = json.loads((artifacts / "apply-receipts.json").read_text(encoding="utf-8"))
    assert receipts["receipts"] and receipts["receipts"][0]["path"] == "buggy_add.py"
    assert receipts["receipts"][0]["checksum_after"]

    # The runtime session used for the follow-up is completed too.
    status_out = server._call_tool(
        "opencontext_session_status",
        {"session_id": handoff["session_id"], "root": str(work)},
    )
    assert status_out["data"]["status"] == "completed"
    server.close()


def test_agent_edits_follow_up_fails_inspection_and_stays_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_mock(monkeypatch)
    work = tmp_path / "proj"
    _write_buggy_project(work)
    server = _server(tmp_path)

    run_out = server._call_tool(
        "opencontext_run",
        {"task": "Fix add: it must return the sum", "workflow": "oc-flow", "root": str(work)},
    )
    handoff = run_out["data"]
    flow = handoff["oc_flow_run"]

    # The agent botches the edit: syntactically broken Python.
    (work / "buggy_add.py").write_text("def add(a, b:\n    return a + b\n", encoding="utf-8")
    args = dict(handoff["follow_up"]["arguments"])
    args["payload"] = dict(args["payload"])
    args["payload"]["changed_files"] = ["buggy_add.py"]
    apply_out = server._call_tool("opencontext_session_apply", args)

    result = apply_out["data"]
    assert result["applied"] is False
    assert result["status"] == "inspection_failed"
    assert result["reason"]

    run_dir = _flow_run_dir(work, flow["session_id"], flow["run_id"])
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "blocked"

    # Retry after fixing the file: the run completes.
    (work / "buggy_add.py").write_text(_FIXED_ADD, encoding="utf-8")
    apply_out = server._call_tool("opencontext_session_apply", args)
    assert apply_out["data"]["applied"] is True
    assert apply_out["data"]["status"] == "completed"
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "completed"
    server.close()


def test_agent_edits_rejects_nonexistent_claimed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_mock(monkeypatch)
    work = tmp_path / "proj"
    _write_buggy_project(work)
    server = _server(tmp_path)

    run_out = server._call_tool(
        "opencontext_run",
        {"task": "Fix add: it must return the sum", "workflow": "oc-flow", "root": str(work)},
    )
    handoff = run_out["data"]

    args = dict(handoff["follow_up"]["arguments"])
    args["payload"] = dict(args["payload"])
    args["payload"]["changed_files"] = ["no_such_file.py"]
    apply_out = server._call_tool("opencontext_session_apply", args)

    result = apply_out["data"]
    assert result["applied"] is False
    assert result["status"] == "rejected"
    assert "no_such_file.py" in result["reason"]
    server.close()


def test_agent_edits_verification_required_runs_provided_test_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A task that demands test verification completes only with test evidence."""
    _pin_mock(monkeypatch)
    work = tmp_path / "proj"
    _write_buggy_project(work)
    (work / "test_buggy_add.py").write_text(
        "from buggy_add import add\n\n\ndef test_add() -> None:\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    server = _server(tmp_path)

    run_out = server._call_tool(
        "opencontext_run",
        {"task": "Fix failing test", "workflow": "oc-flow", "root": str(work)},
    )
    handoff = run_out["data"]
    assert handoff["status"] == "agent_execute"
    flow = handoff["oc_flow_run"]

    (work / "buggy_add.py").write_text(_FIXED_ADD, encoding="utf-8")
    args = dict(handoff["follow_up"]["arguments"])
    args["payload"] = dict(args["payload"])
    args["payload"]["changed_files"] = ["buggy_add.py"]

    # No test evidence yet -> honest needs_verification, run not completed.
    no_tests = server._call_tool("opencontext_session_apply", args)["data"]
    assert no_tests["applied"] is False
    assert no_tests["status"] == "needs_verification"

    # With the test command the run completes with verification evidence.
    args["payload"]["test_command"] = [sys.executable, "-m", "pytest", "-q", "test_buggy_add.py"]
    verified = server._call_tool("opencontext_session_apply", args)["data"]
    assert verified["applied"] is True
    assert verified["status"] == "completed"
    run_dir = _flow_run_dir(work, flow["session_id"], flow["run_id"])
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "completed"
    assert state["verification_outcome"] == "passed"
    assert state["verified_by"]
    server.close()


# --------------------------------------------------------------------------- #
# SDD via MCP: no sampler + no provider -> agent_execute-style handoff.
# --------------------------------------------------------------------------- #


class _FailedHarnessResult:
    run_id = "legacy-run"
    status = "failed"
    artifacts: ClassVar[list[Any]] = []
    gates: ClassVar[list[Any]] = []
    warnings: ClassVar[list[str]] = []
    events: ClassVar[list[Any]] = []
    summary = ""


def test_sdd_run_without_sampler_or_provider_returns_agent_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opencontext_core.harness import runner as runner_mod

    monkeypatch.setattr(
        runner_mod.HarnessRunner, "run", lambda self, w, t, *a, **k: _FailedHarnessResult()
    )
    server = _server(tmp_path)

    out = server._handle_run({"task": "fix the widget", "workflow": "sdd", "root": str(tmp_path)})

    assert out["status"] == "agent_execute"
    assert out["session_id"].startswith("sess-")
    assert out["instructions"]
    assert out["follow_up"]["tool"] == "opencontext_session_apply"
    assert out["follow_up"]["arguments"]["kind"] == "agent_edits"
    # The failed harness verdict stays visible for honesty.
    assert out["harness_status"] == "failed"
    server.close()


def test_sdd_run_with_sampler_keeps_harness_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opencontext_core.harness import runner as runner_mod

    monkeypatch.setattr(
        runner_mod.HarnessRunner, "run", lambda self, w, t, *a, **k: _FailedHarnessResult()
    )
    register_host_sampler(lambda *a: "ok")
    server = _server(tmp_path)

    out = server._handle_run({"task": "fix the widget", "workflow": "sdd", "root": str(tmp_path)})

    assert out["status"] == "failed"
    assert "follow_up" not in out
    server.close()


def test_sdd_agent_edits_follow_up_completes_plain_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SDD handoff completes through the same session apply path (no oc_flow link)."""
    from opencontext_core.harness import runner as runner_mod

    monkeypatch.setattr(
        runner_mod.HarnessRunner, "run", lambda self, w, t, *a, **k: _FailedHarnessResult()
    )
    work = tmp_path / "proj"
    _write_buggy_project(work)
    server = _server(tmp_path)

    out = server._handle_run({"task": "fix the widget", "workflow": "sdd", "root": str(work)})
    assert out["status"] == "agent_execute"

    (work / "buggy_add.py").write_text(_FIXED_ADD, encoding="utf-8")
    args = dict(out["follow_up"]["arguments"])
    args["payload"] = dict(args["payload"])
    args["payload"]["changed_files"] = ["buggy_add.py"]
    result = server._call_tool("opencontext_session_apply", args)["data"]

    assert result["applied"] is True
    assert result["status"] == "completed"
    status_out = server._call_tool(
        "opencontext_session_status", {"session_id": out["session_id"], "root": str(work)}
    )
    assert status_out["data"]["status"] == "completed"
    server.close()


# --------------------------------------------------------------------------- #
# tools/list schema: the follow-up's object parameter must declare properties.
# --------------------------------------------------------------------------- #


def test_session_apply_payload_schema_declares_properties(tmp_path: Path) -> None:
    """``payload`` must declare its nested properties, or strict hosts empty it.

    Observed live: OpenCode 1.17.12 (MiniMax M3) serialized every
    ``opencontext_session_apply`` call with ``payload: {}`` because the
    inputSchema declared a bare ``{"type": "object"}`` — the host/model had no
    declared properties to emit, so the agent_execute follow-up could never
    complete and the run stayed dangling in ``needs_executor``.
    """
    server = _server(tmp_path)
    payload = server.tools["opencontext_session_apply"]["parameters"]["payload"]
    props = payload.get("properties", {})
    assert props.get("changed_files", {}).get("type") == "array"
    assert props.get("test_command", {}).get("type") == "array"
    assert props.get("oc_flow", {}).get("type") == "object"
    oc_flow_props = props.get("oc_flow", {}).get("properties", {})
    assert "session_id" in oc_flow_props
    assert "run_id" in oc_flow_props
    # Forward-compatible: extra payload keys must not be rejected by validators.
    assert payload.get("additionalProperties") is True
    server.close()
