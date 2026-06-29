"""OC Flow definition + edge graph tests (PR-007, FLOW-1, FLOW-2)."""

from __future__ import annotations

from opencontext_core.oc_flow import (
    NodeOutcome,
    oc_flow_definition,
    oc_flow_registry,
    resolve_next_node,
)

_EIGHT_NODES = {
    "init",
    "gather_context",
    "plan",
    "mutate",
    "local_inspection",
    "diagnose",
    "escalation",
    "consolidation",
}


def test_oc_flow_resolves_with_eight_nodes_plus_completed() -> None:
    defn = oc_flow_definition()
    assert set(defn.nodes) == _EIGHT_NODES | {"completed"}
    assert defn.id == "oc-flow"
    assert defn.kind == "oc-flow"
    assert defn.schema_version == "opencontext.workflow.v1"


def test_start_and_terminal_nodes() -> None:
    defn = oc_flow_definition()
    assert defn.start_node == "init"
    assert defn.terminal_nodes == ["completed"]


def test_oc_flow_resolves_from_registry_alongside_sdd() -> None:
    registry = oc_flow_registry()
    assert registry.has("oc-flow")
    assert registry.has("sdd")
    resolved = registry.get("oc-flow")
    assert set(resolved.nodes) == _EIGHT_NODES | {"completed"}


def test_registry_coexistence_no_duplicated_infra() -> None:
    report = oc_flow_registry().validate_coexistence()
    assert report.ok
    assert "oc-flow" in report.kinds
    assert "sdd" in report.kinds
    assert report.duplicated_seams == []


def test_passed_inspection_routes_to_consolidation() -> None:
    defn = oc_flow_definition()
    assert resolve_next_node(defn, "local_inspection", NodeOutcome.PASSED) == "consolidation"


def test_recoverable_failure_routes_to_diagnose() -> None:
    defn = oc_flow_definition()
    assert resolve_next_node(defn, "local_inspection", NodeOutcome.FAILED_RECOVERABLE) == "diagnose"


def test_blocking_failure_routes_to_escalation() -> None:
    defn = oc_flow_definition()
    assert resolve_next_node(defn, "local_inspection", NodeOutcome.FAILED_BLOCKING) == "escalation"


def test_fix_ready_routes_back_to_mutate() -> None:
    defn = oc_flow_definition()
    assert resolve_next_node(defn, "diagnose", NodeOutcome.FIX_READY) == "mutate"


def test_attempts_exhausted_routes_to_escalation() -> None:
    defn = oc_flow_definition()
    assert resolve_next_node(defn, "diagnose", NodeOutcome.ATTEMPTS_EXHAUSTED) == "escalation"


def test_linear_edges_are_unconditional() -> None:
    defn = oc_flow_definition()
    assert resolve_next_node(defn, "init", None) == "gather_context"
    assert resolve_next_node(defn, "gather_context", None) == "plan"
    assert resolve_next_node(defn, "plan", None) == "mutate"
    assert resolve_next_node(defn, "mutate", None) == "local_inspection"
    assert resolve_next_node(defn, "escalation", None) == "consolidation"
    assert resolve_next_node(defn, "consolidation", None) == "completed"


def test_terminal_node_has_no_successor() -> None:
    defn = oc_flow_definition()
    assert resolve_next_node(defn, "completed", None) is None
