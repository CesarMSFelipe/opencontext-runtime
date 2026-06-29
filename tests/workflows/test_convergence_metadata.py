"""Phase CONV — strategy/cost/risk/profile/capability + coexistence tests."""

from __future__ import annotations

import pytest

from opencontext_core.workflows import (
    CostLevel,
    RiskLevel,
    SelectionPolicy,
    WorkflowDefinition,
    WorkflowEdgeDefinition,
    WorkflowNodeDefinition,
    WorkflowProfileError,
    WorkflowRegistry,
    WorkflowResolver,
    WorkflowStrategy,
    validate_coexistence,
)


def _node(node_id: str, role: str = "oc-builder") -> WorkflowNodeDefinition:
    return WorkflowNodeDefinition(id=node_id, label=node_id, role=role, action="run_phase")


def _defn(**overrides: object) -> WorkflowDefinition:
    base: dict[str, object] = dict(
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


def test_strategy_declarable_with_default() -> None:
    """CONV: strategy is declarable and defaults to STANDARD when omitted."""
    assert _defn().strategy == WorkflowStrategy.STANDARD
    assert _defn(strategy="careful").strategy == WorkflowStrategy.CAREFUL


def test_cost_and_risk_declarable() -> None:
    """CONV: expected_cost and risk_level are declarable and accessible."""
    defn = _defn(expected_cost="low", risk_level="medium")
    assert defn.expected_cost == CostLevel.LOW
    assert defn.risk_level == RiskLevel.MEDIUM
    # Defaults applied when omitted.
    assert _defn().expected_cost == CostLevel.MEDIUM
    assert _defn().risk_level == RiskLevel.MEDIUM


def test_default_profile_and_compatible_profiles() -> None:
    """CONV: a workflow declares a default profile and compatible profiles."""
    defn = _defn(default_profile="balanced", compatible_profiles=["balanced", "careful"])
    assert defn.default_profile == "balanced"
    assert defn.compatible_profiles == ["balanced", "careful"]


def test_incompatible_profile_rejected_at_resolve() -> None:
    """CONV: resolving with an incompatible profile raises a typed error."""
    reg = WorkflowRegistry()
    reg.register(_defn(default_profile="balanced", compatible_profiles=["balanced", "careful"]))
    resolver = WorkflowResolver(reg)
    with pytest.raises(WorkflowProfileError):
        resolver.resolve("demo", profile="research")


def test_required_capabilities_declarable() -> None:
    """CONV: required_capabilities is declarable on a workflow."""
    assert _defn(required_capabilities=["pytest"]).required_capabilities == ["pytest"]


def test_missing_capability_degrades_selection() -> None:
    """CONV: selection degrades (with reason) when a required capability is missing."""
    reg = WorkflowRegistry()
    reg.register(
        _defn(
            default_profile="balanced",
            compatible_profiles=["balanced"],
            required_capabilities=["pytest"],
        )
    )
    decision = SelectionPolicy(reg).select(
        intent="localized bugfix",
        profile="balanced",
        capabilities=set(),  # pytest unavailable
        requested="demo",
    )
    assert decision.degraded is True
    assert "pytest" in decision.missing_capabilities
    assert "pytest" in decision.reason


def test_selection_recommends_with_reason() -> None:
    """CONV: selection recommends a workflow id and records a reason (no hidden choice)."""
    reg = WorkflowRegistry.with_builtins()
    decision = SelectionPolicy(reg).select(
        intent="localized bugfix",
        profile="balanced",
        capabilities=set(),
        requested="sdd",
    )
    assert decision.workflow_id == "sdd"
    assert decision.reason  # non-empty, inspectable


def test_sdd_and_oc_flow_coexist() -> None:
    """CONV: SDD and an OC-Flow definition coexist over shared infra (no duplication)."""
    sdd = WorkflowRegistry.with_builtins().get("sdd")
    oc_flow = _defn(
        id="oc-flow",
        kind="oc-flow",
        metadata={
            "runner": "HarnessRunner",
            "event_store": "events.json",
            "receipt_store": "workflow-selection.json",
        },
    )
    report = validate_coexistence([sdd, oc_flow])
    assert report.ok is True
    assert set(report.kinds) == {"sdd", "oc-flow"}
    assert report.shared_runner == "HarnessRunner"
    assert report.duplicated_seams == []


def test_coexistence_flags_duplicated_infra() -> None:
    """CONV: a definition that pins its own runner is flagged as duplicating infra."""
    sdd = WorkflowRegistry.with_builtins().get("sdd")
    rogue = _defn(id="rogue", kind="oc-flow", metadata={"runner": "PrivateRunner"})
    report = validate_coexistence([sdd, rogue])
    assert report.ok is False
    assert any("rogue:runner" in seam for seam in report.duplicated_seams)
