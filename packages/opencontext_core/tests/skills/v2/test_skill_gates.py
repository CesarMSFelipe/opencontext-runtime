"""Tests for skills.v2.gates — gate evaluation blocks registration on FAIL."""

from __future__ import annotations

from opencontext_core.skills.v2.gates import (
    GateOutcome,
    evaluate_gates,
)


def test_fail_gate_blocks_registration() -> None:
    """evaluate_gates returns a FAIL outcome when any gate fails (AND-combined)."""
    gates = [
        ("ruff", GateOutcome.PASS),
        ("mypy", GateOutcome.FAIL),
        ("tests", GateOutcome.PASS),
    ]
    report = evaluate_gates(gates)
    assert report.overall is GateOutcome.FAIL
    assert not report.can_register
    # every gate is recorded, even passing ones
    assert {name for name, _ in gates} == {r.name for r in report.results}
