"""Phase-0 release blocker guards: ruff, mypy, and pytest collection all pass.

Each release-architecture sub-test invokes the tool directly in a subprocess
so a regression is detected without trusting an environment variable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]  # .../tests/release -> repo root


def _run(
    cmd: list[str], *, cwd: Path | None = None, timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_ruff_exits_zero() -> None:
    """`ruff check .` exits with code 0."""
    result = _run([sys.executable, "-m", "ruff", "check", "."])
    assert result.returncode == 0, (
        f"ruff check failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-1000:]}"
    )


def test_mypy_exits_zero() -> None:
    """`mypy packages/opencontext_core` exits with code 0."""
    result = _run([sys.executable, "-m", "mypy", "packages/opencontext_core"])
    assert result.returncode == 0, (
        f"mypy failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-1000:]}"
    )


def test_pytest_collects_nonzero_zero_errors() -> None:
    """`pytest --collect-only -q` collects tests with zero errors."""
    result = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "packages/opencontext_core/tests",
            "-q",
            "--co",
            "--no-header",
        ]
    )
    assert result.returncode == 0, (
        f"pytest collect failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-1000:]}"
    )
    assert " error" not in result.stdout.lower(), result.stdout[-2000:]
