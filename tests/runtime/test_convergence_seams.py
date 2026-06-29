"""Tests for the convergence seams (SPEC RC-CONV).

Profile + capability snapshots on the session, per-run decision log, and the
inert Brain / default Scheduler placeholders.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.runtime.api import RuntimeApi, StartSessionRequest
from opencontext_core.runtime.brain import NullRuntimeBrain
from opencontext_core.runtime.decisions import RuntimeDecision
from opencontext_core.runtime.event_bus import JsonlEventBus
from opencontext_core.runtime.run import RuntimeRun
from opencontext_core.runtime.scheduler import HarnessScheduler
from opencontext_core.runtime.session import RuntimeSession
from opencontext_core.runtime.session_store import SessionStore
from opencontext_core.runtime.state_machine import StateMachine
from opencontext_core.runtime.workflow_runner import WorkflowRunner, WorkflowSpec


class TestSessionSnapshots:
    def test_session_carries_profile_snapshot(self, tmp_path: Path) -> None:
        api = RuntimeApi(tmp_path)
        ref = api.start_session(
            StartSessionRequest(task="do x", root=str(tmp_path), profile="balanced")
        )
        session = SessionStore(tmp_path).load_session(ref.session_id)
        assert session.execution_profile is not None
        assert session.execution_profile.name == "balanced"

    def test_session_captures_detected_capabilities(self, tmp_path: Path) -> None:
        api = RuntimeApi(tmp_path)
        ref = api.start_session(StartSessionRequest(task="do x", root=str(tmp_path)))
        session = SessionStore(tmp_path).load_session(ref.session_id)
        # The snapshot lists the tooling probed at start (keys always present).
        assert "pytest" in session.capability_snapshot
        assert isinstance(session.capability_snapshot["pytest"], bool)


class TestDecisionLog:
    def test_round_trip(self) -> None:
        decision = RuntimeDecision(kind="workflow-selection", chosen="sdd", reason="default")
        reloaded = RuntimeDecision.model_validate_json(decision.model_dump_json())
        assert reloaded.decision_id == decision.decision_id
        assert reloaded.kind == "workflow-selection"
        assert reloaded.chosen == "sdd"
        assert reloaded.reason == "default"

    def test_run_attaches_decision_entries(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path)
        store.create_session(
            RuntimeSession(session_id="sess-1", root=str(tmp_path), task="t", profile="balanced")
        )
        store.create_run(RuntimeRun(run_id="sdd-1", session_id="sess-1", workflow_id="wf"))
        runner = WorkflowRunner(
            store,
            StateMachine(),
            JsonlEventBus(store.events_jsonl("sess-1")),
            workflow=WorkflowSpec("wf", []),
        )

        runner.append_decision(
            "sdd-1", RuntimeDecision(kind="workflow-selection", chosen="sdd", reason="default")
        )

        log = runner.decisions("sdd-1")
        assert len(log.entries) == 1
        assert log.entries[0].chosen == "sdd"
        # Persisted on the run record too.
        assert len(store.load_run("sess-1", "sdd-1").decision_log.entries) == 1


class TestBrainAndSchedulerSeams:
    def test_brain_is_inert(self) -> None:
        brain = NullRuntimeBrain()
        assert brain.recommend(run_id="sdd-1", runtime_context={"gates": {}}) is None

    def test_default_scheduler_delegates_to_harness(self, tmp_path: Path) -> None:
        runner = HarnessRunner(root=tmp_path)
        scheduler = HarnessScheduler()
        assert scheduler.schedule("sdd", harness_runner=runner) == runner.schedule_phases("sdd")
