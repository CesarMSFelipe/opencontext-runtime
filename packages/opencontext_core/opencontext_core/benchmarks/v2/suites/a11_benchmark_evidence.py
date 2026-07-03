"""A11 — benchmark evidence integrity (self-referential).

Verifies that:
1. ``all_suites()`` returns exactly 12 callables.
2. No callable's ``__qualname__`` contains ``_stub`` (the deleted factory marker).

Suite A11 is the self-referential integrity gate: it inspects the live
``_SUITES`` registry at runtime, so any re-introduction of a stub callable
is caught automatically.
"""

from __future__ import annotations

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "A11"
_EXPECTED_COUNT = 12


def run() -> BenchmarkResult:
    """Introspect ``all_suites()`` and assert 12 non-stub callables."""
    # Import locally to avoid a circular import at module load time.
    from opencontext_core.benchmarks.v2.suites import all_suites

    suites = all_suites()

    if len(suites) != _EXPECTED_COUNT:
        return BenchmarkResult(
            name=SUITE_ID,
            success=False,
            methodology_version=current_methodology_version(),
            detail=f"expected {_EXPECTED_COUNT} suites, got {len(suites)}: {sorted(suites)}",
        )

    stub_callables = [
        sid for sid, fn in suites.items() if "_stub" in getattr(fn, "__qualname__", "")
    ]
    if stub_callables:
        return BenchmarkResult(
            name=SUITE_ID,
            success=False,
            methodology_version=current_methodology_version(),
            detail=f"stub callables remaining: {stub_callables}",
        )

    return BenchmarkResult(
        name=SUITE_ID,
        success=True,
        methodology_version=current_methodology_version(),
        detail=f"{_EXPECTED_COUNT} suites registered, no stub callables",
    )
