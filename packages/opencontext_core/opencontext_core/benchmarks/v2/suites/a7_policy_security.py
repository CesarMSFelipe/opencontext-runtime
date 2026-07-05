"""A7 — policy security: policy engine + simulator tests pass.

Runs the policy engine and policy simulator test files via subprocess pytest.
These cover secret detection, forbidden-write denial, and run-blocked enforcement.

Timeout: 120 s.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "A7"
_REPO_ROOT = Path(__file__).resolve().parents[6]
_TIMEOUT = 120

# Policy and gateway test files that cover the security suite.
_TARGETS = [
    "tests/core/test_policy_engine.py",
    "tests/core/test_policy_simulator.py",
    "tests/core/test_egress_policy_engine.py",
]


def run() -> BenchmarkResult:
    """Run policy-security tests and translate exit code honestly."""
    existing = [t for t in _TARGETS if (_REPO_ROOT / t).is_file()]
    if not existing:
        return BenchmarkResult(
            name=SUITE_ID,
            success=False,
            methodology_version=current_methodology_version(),
            detail=(
                "no policy/security test files found at expected paths — "
                "coverage gap; add tests/core/test_policy_engine.py"
            ),
        )

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *existing, "-q", "--tb=short"],
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
        metrics={
            "returncode": proc.returncode,
            "targets": len(existing),
        },
    )
