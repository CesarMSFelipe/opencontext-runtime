"""A3 — SDD feature flow: dispatcher + status contract tests.

Runs subprocess pytest over the strongest existing SDD lifecycle tests:

- ``packages/opencontext_sdd/tests/test_dispatcher.py``
  (RenderDispatcherMarkdown + RenderNativePhasePrompt contract — REQ-OSS-004/005)
- ``packages/opencontext_sdd/tests/test_status.py``
  (canonical Status Pydantic model + Resolve + parse_verify_report — REQ-OSS-001/002/003)

These tests cover the full propose→spec→design→tasks→apply→verify→archive
dispatcher contract without requiring a live LLM or real file tree.

Timeout: 60 s.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "A3"
_REPO_ROOT = Path(__file__).resolve().parents[6]
_TIMEOUT = 60
_TARGETS = [
    "packages/opencontext_sdd/tests/test_dispatcher.py",
    "packages/opencontext_sdd/tests/test_status.py",
]


def run() -> BenchmarkResult:
    """Run SDD dispatcher + status contract tests via subprocess pytest."""
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
