"""Tests for TUI cockpit workflow-state panel (CAP6).

The panel MUST be a pure function over ``WorkflowState``; it MUST NOT hold
its own state. Calling it twice with the same ``WorkflowState`` MUST
produce identical output; changing the state MUST change the output.
"""

from __future__ import annotations

from opencontext_core.oc_new.flow import OC_NEW_FLOW
from opencontext_core.oc_new.models import (
    ChangeIdentity,
    NextAction,
    OcNewRunState,
    PhaseState,
)
from opencontext_core.workflow.panel import render_workflow_panel
from opencontext_core.workflow.state import WorkflowState


def _make_state(current_phase: str | None, blocked: bool = False) -> OcNewRunState:
    identity = ChangeIdentity.from_task("task")
    phases = [PhaseState(name=p.name) for p in OC_NEW_FLOW]
    next_action = (
        NextAction(kind="blocked", phase=current_phase, instruction="blocked")
        if blocked
        else NextAction(kind="spawn_subagent", phase=current_phase or "design", instruction="go")
    )
    return OcNewRunState(
        identity=identity,
        task="task",
        phases=phases,
        current_phase=current_phase,
        blocked_reason="missing" if blocked else None,
        next_action=next_action,
    )


def test_panel_reads_workflow_state_current_phase() -> None:
    state = _make_state("design")
    workflow = WorkflowState.project_from(state)

    panel = render_workflow_panel(workflow)

    assert "design" in panel
    assert "current_phase" in panel or "phase" in panel.lower()


def test_panel_is_pure_no_independent_state() -> None:
    state = _make_state("design")
    workflow = WorkflowState.project_from(state)

    first = render_workflow_panel(workflow)
    second = render_workflow_panel(workflow)
    assert first == second

    workflow2 = WorkflowState.project_from(_make_state("apply"))
    third = render_workflow_panel(workflow2)
    assert third != first
    assert "apply" in third


def test_panel_shows_gate_status() -> None:
    state = _make_state("design", blocked=True)
    workflow = WorkflowState.project_from(state)

    panel = render_workflow_panel(workflow)

    assert workflow.gate.blocked is True
    assert "blocked" in panel.lower()


def test_panel_handles_idle_when_no_current_phase() -> None:
    state = _make_state(current_phase=None)
    workflow = WorkflowState.project_from(state)

    panel = render_workflow_panel(workflow)

    assert workflow.current_phase is None
    assert "idle" in panel.lower() or "—" in panel or "none" in panel.lower()