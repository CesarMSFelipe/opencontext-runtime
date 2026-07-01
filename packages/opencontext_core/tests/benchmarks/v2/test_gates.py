"""Release gates — single source of truth for the 12 gates the 1.0 verdict runs.

The 12-gate tuple is the contract between ``opencontext benchmark
release`` and the 1.0 release evidence. Each gate has a stable name
and a callable runner that returns a :class:`BenchmarkResult`. Missing
runners are an authoring error, not a silent pass.
"""

from __future__ import annotations

import pytest

from opencontext_core.benchmarks.v2.gates import GATES, gate_runner


def test_twelve_gates_exported() -> None:
    """``GATES`` exports exactly 12 entries."""
    assert len(GATES) == 12
    # And every gate is a (name, runner) pair.
    for entry in GATES:
        assert isinstance(entry, tuple)
        assert len(entry) == 2


def test_each_gate_has_callable_runner() -> None:
    """Every gate in ``GATES`` resolves to a callable runner via ``gate_runner``."""
    for name, _ in GATES:
        runner = gate_runner(name)
        assert callable(runner), f"gate {name!r} runner is not callable"


def test_missing_runner_raises() -> None:
    """``gate_runner`` raises ``KeyError`` (or a clear subclass) for unknown gates."""
    with pytest.raises((KeyError, ValueError)):
        gate_runner("definitely-not-a-real-gate-xyz")


def test_gate_names_are_unique() -> None:
    """Gate names are unique — the runner dispatcher relies on a 1:1 name → runner map."""
    names = [name for name, _ in GATES]
    assert len(names) == len(set(names))
