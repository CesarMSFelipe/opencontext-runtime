"""First-run user-flow benchmark suite — §A1 release gate.

Mirrors :mod:`tests.e2e.test_first_run_user_flow` for the
``opencontext benchmark release`` runner. This suite IS §A1 (first_run),
one of the 12 §A release gates for the 1.0 verdict.

The suite itself runs pytest against the e2e test file. If the test
passes (full GREEN), the suite reports success. If the test skips
(honest block) or fails (RED), the suite reports failure with the
exit code in the detail — no silent degradation.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "first_run_user_flow"
_REPO_ROOT = Path(__file__).resolve().parents[6]
_TIMEOUT = 300


def run() -> BenchmarkResult:
    """Run the first-run user-flow E2E pytest and translate the result."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/e2e/test_first_run_user_flow.py",
                "-q",
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(_REPO_ROOT),
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return BenchmarkResult(
            name=SUITE_ID,
            success=False,
            methodology_version=current_methodology_version(),
            detail=f"timeout after {_TIMEOUT}s",
        )
    success = proc.returncode == 0
    out = (proc.stdout or proc.stderr).strip()
    detail = out.splitlines()[-1] if (not success and out) else ""
    return BenchmarkResult(
        name=SUITE_ID,
        success=success,
        methodology_version=current_methodology_version(),
        detail=detail,
        metrics={"returncode": proc.returncode},
    )


# Registry: name → suite callable. Retained for backward compatibility; A1 is
# wired directly in ``suites/__init__.py`` using this module's ``run`` function.
REGISTRY: dict[str, Callable[[], BenchmarkResult]] = {SUITE_ID: run}
