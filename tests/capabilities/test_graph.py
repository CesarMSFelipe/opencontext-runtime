"""CapabilityNode / CapabilityGraph shape and readiness queries (CP-004, CP-005)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.capabilities.graph import (
    CAPABILITY_GRAPH_SCHEMA_VERSION,
    CAPABILITY_NODE_SCHEMA_VERSION,
    CapabilityGraph,
    CapabilityNode,
)


def test_node_schema_version_and_fields() -> None:
    node = CapabilityNode(id="pytest", kind="test", available=True, evidence="pyproject.toml")
    assert node.schema_version == CAPABILITY_NODE_SCHEMA_VERSION == "opencontext.capability_node.v1"
    assert node.available is True
    assert node.evidence == "pyproject.toml"
    assert node.depends_on == []


def test_graph_schema_version_and_get() -> None:
    graph = CapabilityGraph(nodes=[CapabilityNode(id="ruff-check", kind="lint", available=True)])
    assert graph.schema_version == CAPABILITY_GRAPH_SCHEMA_VERSION
    assert graph.schema_version == "opencontext.capability_graph.v1"
    assert graph.get("ruff-check") is not None
    assert graph.get("missing") is None


def test_node_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CapabilityNode(id="x", kind="test", available=True, bogus=1)  # type: ignore[call-arg]


def test_is_ready_false_when_dependency_unavailable() -> None:
    graph = CapabilityGraph(
        nodes=[
            CapabilityNode(
                id="strict_harness", kind="harness", available=True, depends_on=["pytest"]
            ),
        ]
    )
    # pytest is not in the graph at all -> strict_harness is not ready.
    assert graph.is_ready("strict_harness") is False
    assert graph.unmet_dependencies("strict_harness") == ["pytest"]


def test_is_ready_true_when_dependency_ready() -> None:
    graph = CapabilityGraph(
        nodes=[
            CapabilityNode(id="pytest", kind="test", available=True),
            CapabilityNode(
                id="strict_harness", kind="harness", available=True, depends_on=["pytest"]
            ),
        ]
    )
    assert graph.is_ready("pytest") is True
    assert graph.is_ready("strict_harness") is True
    assert graph.unmet_dependencies("strict_harness") == []


def test_is_ready_false_when_dependency_present_but_unavailable() -> None:
    graph = CapabilityGraph(
        nodes=[
            CapabilityNode(id="pytest", kind="test", available=False),
            CapabilityNode(
                id="strict_harness", kind="harness", available=True, depends_on=["pytest"]
            ),
        ]
    )
    assert graph.is_ready("strict_harness") is False
    assert graph.unmet_dependencies("strict_harness") == ["pytest"]


def test_available_ids_returns_only_ready() -> None:
    graph = CapabilityGraph(
        nodes=[
            CapabilityNode(id="pytest", kind="test", available=True),
            CapabilityNode(id="mypy", kind="type", available=False),
            CapabilityNode(
                id="strict_harness", kind="harness", available=True, depends_on=["pytest"]
            ),
        ]
    )
    assert graph.available_ids() == {"pytest", "strict_harness"}


def test_cycle_is_not_ready_and_does_not_recurse_forever() -> None:
    graph = CapabilityGraph(
        nodes=[
            CapabilityNode(id="a", kind="harness", available=True, depends_on=["b"]),
            CapabilityNode(id="b", kind="harness", available=True, depends_on=["a"]),
        ]
    )
    assert graph.is_ready("a") is False
    assert graph.is_ready("b") is False
