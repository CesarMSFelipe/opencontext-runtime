"""Phase-0 ruff clean guard (v2 release blocker, part 2 — sub-test 1/3).

Runs ``ruff check .`` in a subprocess and asserts it exits 0. Per the v2
release-architecture spec, any regression in lint cleanliness is a release
blocker; this test fires on every CI run so the v2 contract is pinned
without trusting an environment variable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ruff_exits_zero() -> None:
    """``ruff check .`` exits with code 0."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"ruff check failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-1000:]}"
    )
