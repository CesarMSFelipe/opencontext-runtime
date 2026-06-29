"""Scheduler governance-invariant tests (RB-004/RB-007/RB-008).

The Brain recommends; the deterministic State Machine governs. A recommendation
the State Machine rejects must not transition, and any override must be recorded
(never silent).
"""

from __future__ import annotations

from opencontext_core.runtime.brain import RuntimeBrain
from opencontext_core.runtime.decisions import SchedulingDecision, SimulationReport
from opencontext_core.runtime.scheduler import RuntimeScheduler
from opencontext_core.runtime.state_machine import StateMachine


def _scheduler() -> RuntimeScheduler:
    return RuntimeScheduler(RuntimeBrain(), state_machine=StateMachine())


def test_schedule_proposes_brain_recommended_successor() -> None:
    scheduler = _scheduler()
    scheduling = scheduler.schedule("run-x", {"current_node": "design", "proposed_node": "apply"})
    assert isinstance(scheduling, SchedulingDecision)
    assert scheduling.next_node.proposed_node == "apply"
    assert scheduling.decision.kind == "next_node"


def test_rejected_recommendation_does_not_transition_and_is_recorded() -> None:
    scheduler = _scheduler()
    scheduling = scheduler.schedule("run-x", {"current_node": "design", "proposed_node": "apply"})
    scheduling, transition = scheduler.govern(
        scheduling,
        required_gates=["spec_approved"],
        runtime_context={"gates": {}},  # gate unmet
    )
    # The State Machine is authoritative: the transition is denied.
    assert transition.allowed is False
    # The current node is unchanged (the Scheduler mutates nothing).
    assert scheduling.next_node.current_node == "design"
    # The override is recorded, not silent (RB-008).
    assert scheduling.decision.governed_by == "state_machine"
    assert "state_machine" in scheduling.decision.reason


def test_allowed_recommendation_keeps_brain_authorship() -> None:
    scheduler = _scheduler()
    scheduling = scheduler.schedule("run-x", {"current_node": "design", "proposed_node": "apply"})
    scheduling, transition = scheduler.govern(
        scheduling, required_gates=[], runtime_context={"gates": {}}
    )
    assert transition.allowed is True
    assert transition.next_node == "apply"
    # No override needed → governed_by stays unset.
    assert scheduling.decision.governed_by is None


def test_simulate_returns_a_typed_stub_report() -> None:
    scheduler = _scheduler()
    report = scheduler.simulate({"run_id": "run-x", "nodes": ["explore", "design", "apply"]})
    assert isinstance(report, SimulationReport)
    assert report.proposed_path == ["explore", "design", "apply"]
    assert report.estimator == "stub"
    assert report.notes  # documents that the real estimator lands with PR-011
