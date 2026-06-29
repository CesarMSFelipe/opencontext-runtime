"""Advisory-only wiring of the Brain into the WorkflowRunner (RB-007/RB-008).

With ``brain_enabled`` False (the default) the runner behaves exactly as PR-001
and writes no decisions. With it on, the Brain only *records* a recommendation;
the State Machine still governs every transition.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.runtime.brain import RuntimeBrain
from opencontext_core.runtime.event_bus import JsonlEventBus
from opencontext_core.runtime.run import RuntimeRun
from opencontext_core.runtime.session import RuntimeSession
from opencontext_core.runtime.session_store import SessionStore
from opencontext_core.runtime.state_machine import StateMachine
from opencontext_core.runtime.workflow_runner import NodeSpec, WorkflowRunner, WorkflowSpec


def _setup(tmp_path: Path) -> SessionStore:
    store = SessionStore(tmp_path)
    store.create_session(
        RuntimeSession(session_id="sess-1", root=str(tmp_path), task="t", profile="balanced")
    )
    store.create_run(RuntimeRun(run_id="run-1", session_id="sess-1", workflow_id="wf"))
    return store


def _runner(store: SessionStore, workflow: WorkflowSpec, **kwargs: object) -> WorkflowRunner:
    return WorkflowRunner(
        store,
        StateMachine(),
        JsonlEventBus(store.events_jsonl("sess-1")),
        workflow=workflow,
        **kwargs,  # type: ignore[arg-type]
    )


def test_flag_off_writes_no_decisions(tmp_path: Path) -> None:
    store = _setup(tmp_path)
    workflow = WorkflowSpec(
        "wf",
        [NodeSpec(node_id="explore", next_node="done"), NodeSpec(node_id="done")],
    )
    runner = _runner(store, workflow)  # brain_enabled defaults False
    result = runner.run_to_completion("run-1")
    assert result.status == "completed"
    assert len(store.load_run("sess-1", "run-1").decision_log) == 0


def test_flag_on_records_advisory_decision_but_state_machine_governs(tmp_path: Path) -> None:
    store = _setup(tmp_path)
    workflow = WorkflowSpec(
        "wf",
        [NodeSpec(node_id="explore", next_node="done"), NodeSpec(node_id="done")],
    )
    runner = _runner(store, workflow, brain=RuntimeBrain(), brain_enabled=True)
    result = runner.run_to_completion("run-1")
    assert result.status == "completed"
    log = store.load_run("sess-1", "run-1").decision_log
    # The single non-terminal node produced one advisory next-node decision.
    assert len(log) == 1
    assert log.entries[0].kind == "next_node"
    # State Machine allowed the transition → no override stamped.
    assert log.entries[0].governed_by is None


def test_flag_on_rejected_transition_is_recorded_and_does_not_advance(tmp_path: Path) -> None:
    store = _setup(tmp_path)
    workflow = WorkflowSpec(
        "wf",
        [
            NodeSpec(node_id="explore", next_node="done", required_gates=["spec_approved"]),
            NodeSpec(node_id="done"),
        ],
    )
    runner = _runner(store, workflow, brain=RuntimeBrain(), brain_enabled=True)
    runner.run_to_completion("run-1")
    run = store.load_run("sess-1", "run-1")
    # Unmet gate → the State Machine blocks; the run stays at explore.
    assert run.current_node == "explore"
    assert run.status == "blocked"
    # The override is recorded, never silent (RB-008).
    log = run.decision_log
    assert len(log) == 1
    assert log.entries[0].governed_by == "state_machine"
