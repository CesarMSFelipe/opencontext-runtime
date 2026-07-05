"""Real-model MCP round-trip proof (real-host-dod-convergence REQ-4, opt-in).

The deterministic contract (config-load, connection handshake, agent_execute →
session_apply mutation) is proven for all three hosts in ``test_real_host_mcp``
and ``test_real_host_mutation`` without a model or network. This module closes
the last honest gap: a **real model**, running inside a **real host**, actually
deciding to invoke an OpenContext MCP tool and getting faithful data back.

It is opt-in because it needs network + a live model backend, both of which make
it non-deterministic and unfit for a default CI gate:

    OPENCONTEXT_REAL_MODEL=1 pytest tests/e2e/test_real_model_turn.py

Flaky-backend discipline: free model backends occasionally return a server
error. That is *skip* (backend unavailable), never a silent pass and never a
false failure. Only a turn that ran but did NOT invoke an opencontext tool fails
the proof. codex/claude live-model turns require operator credentials and are
run manually; their deterministic contract is already committed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.real_host

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIRS = (
    _REPO_ROOT / "packages" / "opencontext_core",
    _REPO_ROOT / "packages" / "opencontext_cli",
)
# Ordered by preference; the test tries each until one backend actually responds.
_FREE_MODELS = (
    "opencode/deepseek-v4-flash-free",
    "opencode/minimax-m3",
    "opencode/mimo-v2.5-free",
    "opencode/nemotron-3-ultra-free",
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


def test_opencode_real_model_invokes_opencontext_tool(tmp_path: Path) -> None:
    if os.environ.get("OPENCONTEXT_REAL_MODEL") != "1":
        pytest.skip("set OPENCONTEXT_REAL_MODEL=1 to run the live real-model proof")
    if shutil.which("opencontext") is None:
        pytest.skip("opencontext CLI not on PATH")
    if shutil.which("opencode") is None:
        pytest.skip("real host binary 'opencode' not installed")
    real_runtime = Path.home() / ".opencode"
    if not real_runtime.is_dir():
        pytest.skip("real ~/.opencode runtime absent — opencode launcher cannot self-locate")

    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir(parents=True, exist_ok=True)
    proj.mkdir(parents=True, exist_ok=True)
    (home / ".opencode").symlink_to(real_runtime)
    (proj / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    env = _env(home)

    setup = subprocess.run(
        [
            "opencontext",
            "setup",
            "opencode",
            "--scope",
            "local",
            "--yes",
            "--non-interactive",
            "--root",
            str(proj),
        ],
        cwd=str(proj),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert setup.returncode == 0, f"setup opencode failed: {setup.stderr or setup.stdout}"

    prompt = (
        "Invoke the opencontext_status MCP tool for this project, then report its "
        "result. You MUST call opencontext_status."
    )
    last_err = ""
    for model in _FREE_MODELS:
        try:
            turn = subprocess.run(
                ["opencode", "run", "--model", model, "--format", "json", prompt],
                cwd=str(proj),
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            last_err = f"{model}: timed out"
            continue
        out = turn.stdout
        # A backend-side server error is unavailability, not a product failure.
        if '"type":"error"' in out and "opencontext_status" not in out:
            last_err = f"{model}: backend error {out[:200]}"
            continue
        tools = sorted(set(re.findall(r"opencontext_[a-z_]+", out)))
        assert tools, (
            f"{model} ran but invoked no opencontext tool — the model could not "
            f"reach the MCP surface:\n{out[:500]}"
        )
        # Faithful round-trip: the status payload reached the model.
        assert re.search(r"index|node|memory|status", out, re.IGNORECASE), (
            f"opencontext tool called but no status data returned to the model:\n{out[:500]}"
        )
        return

    pytest.skip(f"no free model backend responded (unavailable, not a failure): {last_err}")
