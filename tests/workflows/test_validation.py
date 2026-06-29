"""VAL1 — workflow graph validation rule tests."""

from __future__ import annotations

import pytest

from opencontext_core.workflows import (
    WorkflowDefinition,
    WorkflowEdgeDefinition,
    WorkflowNodeDefinition,
    WorkflowRegistry,
    WorkflowValidationError,
    validate,
)
from opencontext_core.workflows.validation import ensure_unique_node_ids


def _node(node_id: str) -> WorkflowNodeDefinition:
    return WorkflowNodeDefinition(id=node_id, label=node_id, role="oc-builder", action="run_phase")


def _defn(**overrides: object) -> WorkflowDefinition:
    base = dict(
        id="demo",
        version="1",
        label="Demo",
        kind="custom",
        start_node="a",
        terminal_nodes=["b"],
        nodes={"a": _node("a"), "b": _node("b")},
        edges=[WorkflowEdgeDefinition(from_node="a", to_node="b")],
    )
    base.update(overrides)
    return WorkflowDefinition(**base)  # type: ignore[arg-type]


def test_valid_sdd_definition_passes() -> None:
    """VAL1: the built-in SDD definition validates without error."""
    sdd = WorkflowRegistry.with_builtins().get("sdd")
    validate(sdd)  # must not raise


def test_edge_to_unknown_node_fails() -> None:
    """VAL1: an edge whose to_node is not a declared node is rejected."""
    defn = _defn(edges=[WorkflowEdgeDefinition(from_node="a", to_node="ghost")])
    with pytest.raises(WorkflowValidationError, match="ghost"):
        validate(defn)


def test_start_node_absent_fails() -> None:
    """VAL1: a start_node not in nodes is rejected."""
    defn = _defn(start_node="missing")
    with pytest.raises(WorkflowValidationError, match="start_node"):
        validate(defn)


def test_terminal_node_absent_fails() -> None:
    """VAL1: a terminal_node not in nodes is rejected."""
    defn = _defn(terminal_nodes=["missing"])
    with pytest.raises(WorkflowValidationError, match="terminal_node"):
        validate(defn)


def test_unreachable_node_fails() -> None:
    """VAL1: a node unreachable from start_node is rejected."""
    defn = _defn(
        nodes={"a": _node("a"), "b": _node("b"), "orphan": _node("orphan")},
        edges=[WorkflowEdgeDefinition(from_node="a", to_node="b")],
        terminal_nodes=["b"],
    )
    with pytest.raises(WorkflowValidationError, match="unreachable"):
        validate(defn)


def test_unreachable_allowed_when_opted_in() -> None:
    """VAL1: metadata.allow_unreachable disables the reachability check."""
    defn = _defn(
        nodes={"a": _node("a"), "b": _node("b"), "orphan": _node("orphan")},
        edges=[WorkflowEdgeDefinition(from_node="a", to_node="b")],
        terminal_nodes=["b"],
        metadata={"allow_unreachable": True},
    )
    validate(defn)  # must not raise


def test_duplicate_node_id_rejected() -> None:
    """VAL1: duplicate node ids are rejected at list-parse time."""
    with pytest.raises(WorkflowValidationError, match="duplicate"):
        ensure_unique_node_ids(["explore", "apply", "explore"])


def test_node_key_id_mismatch_rejected() -> None:
    """VAL1: a node whose key disagrees with its id is rejected."""
    defn = _defn(nodes={"a": _node("a"), "wrongkey": _node("b")}, terminal_nodes=["b"])
    with pytest.raises(WorkflowValidationError, match="disagrees"):
        validate(defn)
