"""First-run user-flow benchmark suite.

Mirrors :mod:`tests.e2e.test_first_run_user_flow` for the
``opencontext benchmark release`` runner. The suite is registered
in :data:`REGISTRY` below; it is intentionally NOT one of the §A1-A12
suites (those are release gates, this is a deliverable artifact).

The suite itself runs pytest against the e2e test file. If the test
passes (full GREEN), the suite reports success. If the test skips
(honest block) or fails (RED), the suite reports failure with the
exit code in the detail — no silent degradation.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "first_run_user_flow"


def run() -> BenchmarkResult:
    """Run the first-run user-flow E2E pytest and translate the result."""
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
    )
    success = proc.returncode == 0
    detail = (proc.stdout or proc.stderr).strip().splitlines()[-1] if not success else ""
    return BenchmarkResult(
        name=SUITE_ID,
        success=success,
        methodology_version=current_methodology_version(),
        detail=detail,
        metrics={"returncode": proc.returncode},
    )


# Registry: name → suite callable. ``all_suites()`` is consumed by
# the release runner; ``first_run_user_flow`` is exposed alongside
# the §A1-A12 set without being one of them.
REGISTRY: dict[str, Callable[[], BenchmarkResult]] = {SUITE_ID: run}
