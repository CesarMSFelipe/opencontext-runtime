"""Phase-0 mypy clean guard (v2 release blocker, part 2 — sub-test 2/3).

Runs ``mypy packages/opencontext_core`` (the v1 stepping-stone scope; full
multi-package mypy lands in commits 014 + 022) in a subprocess and asserts
it exits 0 under ``--strict``. Strict TDD pin for the v2 release gate.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_mypy_exits_zero() -> None:
    """``mypy packages/opencontext_core`` exits with code 0 under --strict."""
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "packages/opencontext_core"],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        f"mypy failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-1000:]}"
    )
