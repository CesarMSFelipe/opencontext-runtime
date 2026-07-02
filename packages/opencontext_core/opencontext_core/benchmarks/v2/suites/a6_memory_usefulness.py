"""A6 — memory usefulness: save/search roundtrip + promotion policy.

Exercises the memory v2 promotion policy: a generic (no-op) run must be
rated ``not_promoted`` (composite < 0.6). Runs via subprocess pytest over:

- ``packages/opencontext_core/tests/memory/v2/test_promotion.py``
  (unit: quality thresholds, evaluate_promotion behaviour)
- ``tests/integration/test_memory_promotion_policy.py``
  (integration: real OC Flow node_consolidation records promotion=not_promoted
  for a generic task)

Timeout: 120 s.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "A6"
_REPO_ROOT = Path(__file__).resolve().parents[6]
_TIMEOUT = 120
_TARGETS = [
    "packages/opencontext_core/tests/memory/v2/test_promotion.py",
    "tests/integration/test_memory_promotion_policy.py",
]


def run() -> BenchmarkResult:
    """Run memory promotion policy tests and translate exit code honestly."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *_TARGETS, "-q", "--tb=short"],
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
