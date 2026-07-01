"""Phase-0 pytest-collect guard (v2 release blocker, part 2 — sub-test 3/3).

Runs ``pytest packages/opencontext_core/tests --collect-only`` in a subprocess
and asserts it exits 0 with no collection errors. Companion to the
fine-grained ``test_phase0_collects_clean.py`` — this test asserts the
process-level exit code independently so a subprocess runner, an env
quirk, or a runtime collect hook can't mask a regression.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_TESTS_ROOT = REPO_ROOT / "packages" / "opencontext_core" / "tests"


def test_pytest_collects_nonzero_zero_errors() -> None:
    """``pytest --collect-only -q`` collects tests with zero errors."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(CORE_TESTS_ROOT),
            "-q",
            "--co",
            "--no-header",
        ],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"pytest collect failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-1000:]}"
    )
    assert " error" not in result.stdout.lower(), result.stdout[-2000:]
