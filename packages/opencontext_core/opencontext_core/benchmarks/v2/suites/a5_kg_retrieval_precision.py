"""A5 — knowledge-graph retrieval precision.

Exercises the KG indexing pipeline against a seeded call-chain project and
asserts that callers/callees are captured with correct edges. Runs the
``test_kg_indexing_truth.py`` harness via subprocess pytest.

Timeout: 180 s (KG indexing + tree-sitter grammar load).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "A5"
_REPO_ROOT = Path(__file__).resolve().parents[6]
_TIMEOUT = 180


def run() -> BenchmarkResult:
    """Run KG indexing truth tests and translate the exit code honestly."""
    target = "packages/opencontext_core/tests/indexing/test_kg_indexing_truth.py"
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", target, "-q", "--tb=short"],
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
