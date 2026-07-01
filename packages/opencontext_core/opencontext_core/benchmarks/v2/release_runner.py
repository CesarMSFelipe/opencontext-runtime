"""Release runner — combines 12 gates + 12 §A suites into a single verdict.

The release runner is the library surface for ``opencontext benchmark
release``. It runs every gate from :mod:`opencontext_core.benchmarks.v2.gates`
and every §A suite from :mod:`opencontext_core.benchmarks.v2.suites`,
then renders a :class:`ReleaseVerdict` whose ``verdict`` string is the
1.0_READY / 1.0_NOT_READY outcome the CLI exits on.

Profiles: ``balanced`` (default — all gates + all suites),
``fastest`` (subset of cheap gates), ``cheapest`` (subset of suites
that don't require heavy fixtures), ``highest_quality`` (full set).
Profiles are pure data; the runner applies them as filters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from opencontext_core.benchmarks.v2.gates import GATES
from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult
from opencontext_core.benchmarks.v2.suites import all_suites

# Profile → subset of suites to run. ``balanced`` and ``highest_quality``
# run all 12; ``fastest`` and ``cheapest`` trim to a 6-suite subset.
PROFILE_SUITES: Final[dict[str, tuple[str, ...]]] = {
    "balanced": tuple(f"A{i}" for i in range(1, 13)),
    "fastest": ("A1", "A3", "A6", "A8", "A9", "A10"),
    "cheapest": ("A1", "A2", "A3", "A6", "A8", "A10"),
    "highest_quality": tuple(f"A{i}" for i in range(1, 13)),
}


@dataclass
class ReleaseVerdict:
    """The 1.0 release verdict: gate + suite results + outcome string."""

    profile: str
    results: list[BenchmarkResult] = field(default_factory=list)
    verdict: str = "1.0_NOT_READY"
    methodology_version: str = current_methodology_version()


def release_gate_names() -> tuple[str, ...]:
    """Return the tuple of gate names in declaration order."""
    return tuple(name for name, _ in GATES)


def suite_names_for_profile(profile: str) -> tuple[str, ...]:
    """Return the suite ids selected by ``profile``."""
    if profile not in PROFILE_SUITES:
        raise ValueError(f"unknown profile: {profile!r}")
    return PROFILE_SUITES[profile]


def _run_gates() -> list[BenchmarkResult]:
    """Run every gate declared in :data:`GATES` in order."""
    return [runner() for _, runner in GATES]


def _run_suites_for_profile(profile: str) -> list[BenchmarkResult]:
    """Run the suites selected by ``profile``."""
    suites = all_suites()
    return [suites[sid]() for sid in suite_names_for_profile(profile) if sid in suites]


def _compute_verdict(results: list[BenchmarkResult]) -> str:
    """Translate a list of results into the 1.0_READY / 1.0_NOT_READY string."""
    if not results:
        return "1.0_NOT_READY"
    return "1.0_READY" if all(r.success for r in results) else "1.0_NOT_READY"


def run_release(
    *, profile: str = "balanced", run_gates: bool = True, run_suites: bool = True
) -> ReleaseVerdict:
    """Run the 1.0 release verdict for ``profile``.

    The ``run_gates`` / ``run_suites`` flags exist for tests; the CLI
    always passes both as ``True``.
    """
    if profile not in PROFILE_SUITES:
        raise ValueError(f"unknown profile: {profile!r}")
    results: list[BenchmarkResult] = []
    if run_gates:
        results.extend(_run_gates())
    if run_suites:
        results.extend(_run_suites_for_profile(profile))
    return ReleaseVerdict(
        profile=profile,
        results=results,
        verdict=_compute_verdict(results),
        methodology_version=current_methodology_version(),
    )
