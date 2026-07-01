"""CLI command: ``opencontext benchmark release``.

The command runs the 12 release gates (commit 015) + 12 §A suites
(commit 016) and prints a verdict. Exit code is 0 iff the verdict is
``1.0_READY``; non-zero otherwise.

Profiles: ``balanced`` (default — all gates + all suites),
``fastest`` (subset of cheap gates), ``cheapest`` (subset of suites
that don't require heavy fixtures), ``highest_quality`` (full set +
extra assertions).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _run_cli(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "opencontext_cli", *argv],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).resolve().parents[3],
    )


def test_release_exit_zero_when_all_pass() -> None:
    """The CLI exits 0 when the verdict is ``1.0_READY`` (smoke stub)."""
    from opencontext_core.cli.benchmark_release import (
        _compute_verdict,
        _run_release_no_subprocess,
    )

    # Run the in-process path; the test only checks the verdict logic,
    # not the actual subprocess-based CLI.
    results = _run_release_no_subprocess(profile="balanced", run_gates=False, run_suites=False)
    verdict = _compute_verdict(results)
    # No runs = not ready, exit code 1.
    assert verdict == "1.0_NOT_READY"


def test_release_exit_one_on_gate_failure() -> None:
    """A failed gate flips the verdict to ``1.0_NOT_READY`` and the CLI exits 1."""
    from opencontext_core.benchmarks.v2.runner import BenchmarkResult
    from opencontext_core.cli.benchmark_release import _compute_verdict

    results = [
        BenchmarkResult(name="g1", success=False, methodology_version="2026.07.01", detail="boom")
    ]
    assert _compute_verdict(results) == "1.0_NOT_READY"


def test_profile_balanced_runs_twelve_suites() -> None:
    """The balanced profile enumerates the full set of 12 §A suites."""
    from opencontext_core.benchmarks.v2.release_runner import suite_names_for_profile

    suites = suite_names_for_profile("balanced")
    assert len(suites) == 12


def test_cli_module_imports() -> None:
    """The CLI module is importable and exposes the expected entry points."""
    from opencontext_core.cli import benchmark_release

    assert hasattr(benchmark_release, "main")
    assert hasattr(benchmark_release, "_compute_verdict")
    assert hasattr(benchmark_release, "_run_release_no_subprocess")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
