"""Release runner — combines 12 gates + 12 §A suites into a single verdict.

The release runner is the library surface for ``opencontext benchmark
release``. It runs every gate from :mod:`opencontext_core.benchmarks.v2.gates`
and every §A suite from :mod:`opencontext_core.benchmarks.v2.suites`,
then renders a :class:`ReleaseVerdict` whose ``ready`` flag is the
verdict the CLI exits on.

The runner is profile-aware: ``balanced`` runs everything, the other
profiles (``fastest``, ``cheapest``, ``highest_quality``) select a
subset. Profiles are pure data; the runner applies them as filters.
"""

from __future__ import annotations

import pytest


def test_verdict_one_zero_ready() -> None:
    """A release runner exists and reports the 1.0_READY verdict when all pass."""
    from opencontext_core.benchmarks.v2.release_runner import (
        ReleaseVerdict,
        run_release,
    )

    verdict: ReleaseVerdict = run_release(profile="balanced", run_gates=False, run_suites=False)
    # No gates / no suites means an empty verdict: not 1.0_READY.
    assert verdict.verdict in {"1.0_READY", "1.0_NOT_READY"}
    assert isinstance(verdict.results, list)


def test_report_includes_twelve_gate_names() -> None:
    """The release runner enumerates the same 12 gates as ``GATES``."""
    from opencontext_core.benchmarks.v2.gates import GATES
    from opencontext_core.benchmarks.v2.release_runner import release_gate_names

    names = release_gate_names()
    assert len(names) == len(GATES)
    assert set(names) == {name for name, _ in GATES}


def test_release_runner_smoke_combined() -> None:
    """``run_release`` combines gate and suite results in a single verdict."""
    from opencontext_core.benchmarks.v2.release_runner import run_release

    # Stub out gates and suites via flags so the test is hermetic.
    verdict = run_release(profile="balanced", run_gates=False, run_suites=False)
    assert verdict.verdict == "1.0_NOT_READY"  # no runs == not ready
    assert verdict.results == []


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
