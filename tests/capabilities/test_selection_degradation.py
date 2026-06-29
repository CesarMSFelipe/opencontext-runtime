"""Capability-driven selection & graceful gate degradation (CP-011 / CP-CONV)."""

from __future__ import annotations

from opencontext_core.capabilities.graph import CapabilityGraph, CapabilityNode
from opencontext_core.workflows.capability_selection import CapabilityAwareSelection
from opencontext_core.workflows.registry import WorkflowRegistry


def _no_linter_graph() -> CapabilityGraph:
    # pytest present, ruff (linter) absent.
    return CapabilityGraph(nodes=[CapabilityNode(id="pytest", kind="test", available=True)])


def test_missing_linter_downgrades_not_fails() -> None:
    bridge = CapabilityAwareSelection(
        WorkflowRegistry(), graph=_no_linter_graph(), enabled=True
    )

    plan = {d.gate: d for d in bridge.degrade_gates({"lint": "ruff-check", "tests": "pytest"})}

    # Lint gate downgraded to advisory with a recorded, actionable note; run continues.
    assert plan["lint"].downgraded is True
    assert "advisory" in plan["lint"].note
    assert "ruff-check" in plan["lint"].note
    # Tests gate stays enforced (its capability is available).
    assert plan["tests"].downgraded is False


def test_available_capabilities_feed_selection_when_enabled() -> None:
    bridge = CapabilityAwareSelection(
        WorkflowRegistry(), graph=_no_linter_graph(), enabled=True
    )
    assert bridge.available_capabilities() == {"pytest"}


def test_flag_disabled_restores_legacy_behaviour() -> None:
    # enabled=False (runtime.execution_profile == "") -> no capability influence.
    bridge = CapabilityAwareSelection(
        WorkflowRegistry(), graph=_no_linter_graph(), enabled=False
    )
    assert bridge.enabled is False
    assert bridge.available_capabilities() == set()
    plan = bridge.degrade_gates({"lint": "ruff-check"})
    assert plan[0].downgraded is False  # nothing degrades when the flag is off


def test_from_config_empty_profile_disables_bridge() -> None:
    bridge = CapabilityAwareSelection.from_config(
        WorkflowRegistry(), "", graph=_no_linter_graph()
    )
    assert bridge.enabled is False

    enabled = CapabilityAwareSelection.from_config(
        WorkflowRegistry(), "balanced", graph=_no_linter_graph()
    )
    assert enabled.enabled is True
