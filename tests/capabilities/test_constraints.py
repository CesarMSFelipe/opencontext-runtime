"""CapabilityConstraint evaluation with actionable messages (CP-005)."""

from __future__ import annotations

from opencontext_core.capabilities.constraints import CapabilityConstraint
from opencontext_core.capabilities.graph import CapabilityGraph, CapabilityNode


def _graph(*nodes: CapabilityNode) -> CapabilityGraph:
    return CapabilityGraph(nodes=list(nodes))


def test_constraint_unsatisfied_returns_missing_with_message() -> None:
    constraint = CapabilityConstraint(
        capability_id="strict_harness",
        requires=["pytest"],
        message="Install pytest to enable a strict harness.",
    )
    graph = _graph(CapabilityNode(id="ruff-check", kind="lint", available=True))

    satisfied, missing = constraint.evaluate(graph)

    assert satisfied is False
    assert missing == ["pytest"]
    assert constraint.message  # actionable UX is present


def test_constraint_satisfied_when_requirement_ready() -> None:
    constraint = CapabilityConstraint(capability_id="strict_harness", requires=["pytest"])
    graph = _graph(CapabilityNode(id="pytest", kind="test", available=True))

    satisfied, missing = constraint.evaluate(graph)

    assert satisfied is True
    assert missing == []


def test_constraint_treats_unavailable_requirement_as_missing() -> None:
    constraint = CapabilityConstraint(capability_id="x", requires=["pytest"])
    graph = _graph(CapabilityNode(id="pytest", kind="test", available=False))

    satisfied, missing = constraint.evaluate(graph)

    assert satisfied is False
    assert missing == ["pytest"]
