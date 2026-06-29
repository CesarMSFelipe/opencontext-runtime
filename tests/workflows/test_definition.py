"""WD1 / WN1 / WE1 — WorkflowDefinition schema model tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.workflows import (
    WORKFLOW_SCHEMA_VERSION,
    WorkflowDefinition,
    WorkflowEdgeDefinition,
    WorkflowNodeDefinition,
    node_uid,
    workflow_uid,
)


def _node(node_id: str, role: str = "oc-builder") -> WorkflowNodeDefinition:
    return WorkflowNodeDefinition(id=node_id, label=node_id.title(), role=role, action="run_phase")


def test_definition_constructable_with_default_schema_version() -> None:
    """WD1: a valid definition constructs and defaults schema_version."""
    defn = WorkflowDefinition(
        id="demo",
        version="1",
        label="Demo",
        kind="custom",
        start_node="a",
        terminal_nodes=["b"],
        nodes={"a": _node("a"), "b": _node("b")},
        edges=[WorkflowEdgeDefinition(from_node="a", to_node="b")],
    )
    assert defn.schema_version == WORKFLOW_SCHEMA_VERSION == "opencontext.workflow.v1"
    assert defn.uid == workflow_uid("demo") == "wf_demo"


def test_node_carries_persona_harnesses_and_outputs() -> None:
    """WN1: a node carries role, required_harnesses, and required_outputs."""
    node = WorkflowNodeDefinition(
        id="apply",
        label="Apply",
        role="oc-builder",
        action="run_phase",
        required_harnesses=["mutation", "security"],
        required_outputs=["apply-manifest.json"],
    )
    assert node.role == "oc-builder"
    assert node.required_harnesses == ["mutation", "security"]
    assert node.required_outputs == ["apply-manifest.json"]
    assert node.uid == node_uid("apply") == "node_apply"


def test_node_lists_default_to_empty() -> None:
    """WN1: omitted node lists default to empty lists."""
    node = _node("explore", role="oc-explorer")
    assert node.required_personas == []
    assert node.required_skills == []
    assert node.required_harnesses == []
    assert node.required_outputs == []
    assert node.gates == []


def test_conditional_edge_representable() -> None:
    """WE1: an edge can carry an optional condition."""
    edge = WorkflowEdgeDefinition(
        from_node="local_inspection",
        to_node="diagnose",
        condition="inspection_failed_recoverable",
    )
    assert edge.condition == "inspection_failed_recoverable"


def test_edge_condition_defaults_to_none() -> None:
    """WE1: condition defaults to None."""
    assert WorkflowEdgeDefinition(from_node="a", to_node="b").condition is None


def test_definition_rejects_unknown_field() -> None:
    """extra='forbid' guards against typos / schema drift."""
    with pytest.raises(ValidationError):
        WorkflowNodeDefinition(  # type: ignore[call-arg]
            id="a", label="A", role="r", action="run_phase", bogus=True
        )


def test_phase_order_topologically_orders_nodes() -> None:
    """phase_order resolves declared nodes through the edges (DAG order)."""
    defn = WorkflowDefinition(
        id="demo",
        version="1",
        label="Demo",
        kind="custom",
        start_node="a",
        terminal_nodes=["c"],
        nodes={"a": _node("a"), "b": _node("b"), "c": _node("c")},
        edges=[
            WorkflowEdgeDefinition(from_node="a", to_node="b"),
            WorkflowEdgeDefinition(from_node="b", to_node="c"),
        ],
    )
    assert defn.phase_order() == ["a", "b", "c"]
