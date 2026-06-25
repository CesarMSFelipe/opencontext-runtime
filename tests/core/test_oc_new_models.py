"""Tests for oc_new models."""

from __future__ import annotations

import pytest

from opencontext_core.oc_new.flow import OC_NEW_FLOW
from opencontext_core.oc_new.models import (
    AgentHandoff,
    ChangeIdentity,
    OcNewRunState,
    PhaseState,
    render_handoff_markdown,
)


def test_change_identity_from_task_slug():
    identity = ChangeIdentity.from_task("Add graph health command")
    assert identity.change_id == "add-graph-health-command"
    assert identity.run_id.startswith("ocnew-")
    assert identity.trace_id.startswith("trace-")
    assert identity.memory_key == "change:add-graph-health-command"


def test_change_identity_empty_task():
    identity = ChangeIdentity.from_task("   ")
    assert identity.change_id.startswith("change-")


def test_oc_new_run_state_phase_lookup():
    phases = [PhaseState(name=p.name) for p in OC_NEW_FLOW]
    identity = ChangeIdentity.from_task("test task")
    state = OcNewRunState(identity=identity, task="test task", phases=phases)
    phase = state.phase("explore")
    assert phase.name == "explore"
    assert phase.status == "pending"


def test_oc_new_run_state_phase_lookup_missing():
    phases = [PhaseState(name=p.name) for p in OC_NEW_FLOW]
    identity = ChangeIdentity.from_task("test task")
    state = OcNewRunState(identity=identity, task="test task", phases=phases)
    with pytest.raises(KeyError):
        state.phase("nonexistent")  # type: ignore[arg-type]


def test_completed_phases_empty():
    phases = [PhaseState(name=p.name) for p in OC_NEW_FLOW]
    identity = ChangeIdentity.from_task("test task")
    state = OcNewRunState(identity=identity, task="test task", phases=phases)
    assert state.completed_phases() == []


def test_render_handoff_markdown():
    handoff = AgentHandoff(
        run_id="ocnew-abc",
        change_id="add-graph-health",
        trace_id="trace-xyz",
        phase="explore",
        persona="oc-explorer",
        task="Add graph health command",
        memory_key="change:add-graph-health",
        required_inputs=["context-pack.json"],
        expected_outputs=["explore.artifact.json"],
        allowed_tools=["opencontext_context"],
    )
    md = render_handoff_markdown(handoff)
    assert "ocnew-abc" in md
    assert "oc-explorer" in md
    assert "explore.artifact.json" in md
    assert "context-pack.json" in md
