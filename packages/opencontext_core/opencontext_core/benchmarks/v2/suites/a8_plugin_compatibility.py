"""A8 — plugin compatibility: plugin SDK and conformance tests pass.

Runs the plugin conformance, lifecycle, and manifest test files via subprocess
pytest to verify the plugin SDK surface is stable.

Timeout: 120 s.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "A8"
_REPO_ROOT = Path(__file__).resolve().parents[6]
_TIMEOUT = 120

# Plugin SDK / compatibility test files.
_TARGETS = [
    "tests/core/test_plugin_conformance.py",
    "tests/core/test_plugin_lifecycle.py",
    "packages/opencontext_core/tests/plugins/v2/test_conformance.py",
    "packages/opencontext_core/tests/plugins/v2/test_lifecycle.py",
]


def run() -> BenchmarkResult:
    """Run plugin compatibility tests and translate exit code honestly."""
    existing = [t for t in _TARGETS if (_REPO_ROOT / t).is_file()]
    if not existing:
        return BenchmarkResult(
            name=SUITE_ID,
            success=False,
            methodology_version=current_methodology_version(),
            detail=(
                "no plugin compatibility test files found at expected paths — "
                "coverage gap; add tests/core/test_plugin_conformance.py"
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
