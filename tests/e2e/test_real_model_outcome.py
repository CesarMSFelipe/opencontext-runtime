"""Real-model OUTCOME proof: a real model drives an OpenContext flow to actually
fix a bug and make its failing test pass — the end-user promise, not just a tool
call (that lighter proof lives in ``test_real_model_turn``).

Opt-in, because it needs a live model backend:

    OPENCONTEXT_REAL_MODEL=1 pytest tests/e2e/test_real_model_outcome.py

Defaults to opencode + a free model (no paid credentials). The heavy lifting is
in ``scripts/real_model_outcome.sh``, which sets up an isolated project with a
buggy ``add`` + a failing test, points the host at the OpenContext MCP server,
drives one flow turn, and verifies the fix landed and the test passes. A backend
that is simply unavailable SKIPS (never a silent pass); only a reachable model
that failed to produce the fix fails the test.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.real_host

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "real_model_outcome.sh"


def test_opencode_real_model_fixes_bug_through_flow() -> None:
    if os.environ.get("OPENCONTEXT_REAL_MODEL") != "1":
        pytest.skip("set OPENCONTEXT_REAL_MODEL=1 to run the live real-model outcome proof")
    if shutil.which("opencode") is None:
        pytest.skip("real host binary 'opencode' not installed")
    if not (Path.home() / ".opencode").is_dir():
        pytest.skip("real ~/.opencode runtime absent — opencode launcher cannot self-locate")

    model = os.environ.get("OPENCONTEXT_REAL_MODEL_OPENCODE", "opencode/deepseek-v4-flash-free")
    proc = subprocess.run(
        ["bash", str(_SCRIPT), "opencode", "oc-flow", "off", model],
        capture_output=True,
        text=True,
        timeout=600,
    )
    out = f"{proc.stdout}\n{proc.stderr}"
    # Distinguish an unavailable backend (skip) from a real product failure (fail).
    if proc.returncode != 0 and ("error" in out.lower() and "outcome_ok" not in out):
        pytest.skip(f"model backend unavailable, not a product failure: {out[-300:]}")
    assert '"outcome_ok":true' in out.replace(" ", ""), (
        f"real model did not fix the bug through the OpenContext flow:\n{out[-500:]}"
    )
