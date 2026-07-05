"""A9 — provider fallback: fallback tests pass.

Verifies provider-fallback coverage by running the existing fallback test
files via subprocess pytest.  Fallback test files are checked for existence
first — an absent file returns success=False naming the gap (HONESTY RULE 2).

Timeout: 120 s.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "A9"
_REPO_ROOT = Path(__file__).resolve().parents[6]
_TIMEOUT = 120

# Provider fallback test files verified to exist at B3 implementation time.
_TARGETS = [
    "packages/opencontext_core/tests/providers/v2/test_fallback.py",
    "tests/providers/test_provider_gateway_v2_fallback.py",
]


def run() -> BenchmarkResult:
    """Run provider-fallback tests and translate exit code honestly."""
    existing = [t for t in _TARGETS if (_REPO_ROOT / t).is_file()]
    if not existing:
        # HONESTY RULE 2: if no fallback tests exist, report the gap honestly.
        return BenchmarkResult(
            name=SUITE_ID,
            success=False,
            methodology_version=current_methodology_version(),
            detail=(
                "no provider-fallback test files found at expected paths — "
                "coverage gap: add packages/opencontext_core/tests/providers/v2/test_fallback.py"
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
