"""A10 — resume + rollback: checkpoint/resume tests.

Runs subprocess pytest over the checkpoint-backed rollback and harness resume
tests that prove:

- Post-apply failure rolls the workspace back to the pre-edit checkpoint
  (``tests/harness/test_apply_checkpoint_rollback.py``)
- Resume restores the run contract and diagnosis attempts from persisted state
  (``tests/core/test_harness_resume.py``)

Both files are fast (pure-data, no subprocess calls) and together cover the
checkpoint → rollback and resume → contract-restoration semantics.

Timeout: 60 s.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "A10"
_REPO_ROOT = Path(__file__).resolve().parents[6]
_TIMEOUT = 60
_TARGETS = [
    "tests/harness/test_apply_checkpoint_rollback.py",
    "tests/core/test_harness_resume.py",
]


def run() -> BenchmarkResult:
    """Run checkpoint/resume tests via subprocess pytest."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *_TARGETS,
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(_REPO_ROOT),
            env={**__import__("os").environ, "OPENCONTEXT_STORAGE_MODE": "local"},
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
