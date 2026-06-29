"""Tests for the WorkflowRunner and the 14-step pipeline (SPEC RC-008/010/011)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.runtime.event_bus import CollectingConsumer
from opencontext_core.runtime.modes import RuntimeMode
from opencontext_core.runtime.run import NodeResult, RuntimeRun
from opencontext_core.runtime.session import RuntimeSession
from opencontext_core.runtime.session_store import SessionStore
from opencontext_core.runtime.state_machine import StateMachine
from opencontext_core.runtime.workflow_runner import (
    ExecutionContext,
    NodeSpec,
    WorkflowRunner,
    WorkflowSpec,
)


def _setup(tmp_path: Path, *, capabilities: dict[str, bool] | None = None):
    store = SessionStore(tmp_path)
    session = RuntimeSession(
        session_id="sess-1",
        root=str(tmp_path),
        task="do x",
        profile="balanced",
        capability_snapshot=capabilities or {},
    )
    store.create_session(session)
    store.create_run(RuntimeRun(run_id="sdd-1", session_id="sess-1", workflow_id="wf"))
    return store


def _ok_node(node_id: str, next_node: str | None) -> NodeSpec:
    def action(ctx: ExecutionContext) -> NodeResult:
        return NodeResult(
            session_id=ctx.session_id,
            run_id=ctx.run_id,
            workflow_id=ctx.workflow_id,
            node_id=ctx.node_id,
            status="completed",
            summary="ok",
        )

    return NodeSpec(node_id=node_id, next_node=next_node, action=action)


class TestStep:
    def test_step_advances_current_node(self, tmp_path: Path) -> None:
        store = _setup(tmp_path)
        bus = store.event_bus("sess-1")
        workflow = WorkflowSpec("wf", [_ok_node("n1", "n2"), _ok_node("n2", None)])
        runner = WorkflowRunner(store, StateMachine(), bus, workflow=workflow)

        action = runner.step("sdd-1")
        assert action.kind == "execute_node"
        assert action.node_id == "n2"
        assert store.load_run("sess-1", "sdd-1").current_node == "n2"


class TestRunToCompletion:
    def test_runs_all_nodes(self, tmp_path: Path) -> None:
        store = _setup(tmp_path)
        bus = store.event_bus("sess-1")
        workflow = WorkflowSpec("wf", [_ok_node("n1", "n2"), _ok_node("n2", None)])
        runner = WorkflowRunner(store, StateMachine(), bus, workflow=workflow)

        result = runner.run_to_completion("sdd-1")
        assert result.status == "completed"
        assert [n.node_id for n in result.node_results] == ["n1", "n2"]


class TestExecuteNodeFailure:
    def test_action_raises_is_captured(self, tmp_path: Path) -> None:
        store = _setup(tmp_path)
        bus = store.event_bus("sess-1")

        def boom(ctx: ExecutionContext) -> NodeResult:
            raise RuntimeError("kaboom")

        workflow = WorkflowSpec("wf", [NodeSpec(node_id="n1", next_node=None, action=boom)])
        runner = WorkflowRunner(store, StateMachine(), bus, workflow=workflow)

        result = runner.execute_node("sdd-1", "n1")
        assert result.status == "failed"
        assert result.error is not None
        assert "kaboom" in result.error


class TestCapabilityGate:
    def test_missing_capability_short_circuits(self, tmp_path: Path) -> None:
        store = _setup(tmp_path, capabilities={"pytest": True})
        bus = store.event_bus("sess-1")
        collector = CollectingConsumer()
        bus.subscribe(collector)
        node = NodeSpec(node_id="n1", required_capabilities=["docker"], next_node=None)
        workflow = WorkflowSpec("wf", [node])
        runner = WorkflowRunner(store, StateMachine(), bus, workflow=workflow)

        result = runner.execute_node("sdd-1", "n1")
        assert result.status == "failed"
        assert result.error is not None
        assert "capability_missing" in result.error
        # A node event recording the missing capability is emitted.
        cap_events = [e for e in collector.events if e.type == "node.capability_missing"]
        assert cap_events
        assert "docker" in cap_events[0].metadata.get("missing_capabilities", [])


class TestDryRun:
    def test_dry_run_performs_no_mutation_or_persist(self, tmp_path: Path) -> None:
        store = _setup(tmp_path)
        bus = store.event_bus("sess-1")
        marker = tmp_path / "mutated.txt"
        persisted: list[NodeResult] = []

        def action(ctx: ExecutionContext) -> NodeResult:
            if not ctx.dry_run:
                marker.write_text("x", encoding="utf-8")
            return NodeResult(
                session_id=ctx.session_id,
                run_id=ctx.run_id,
                workflow_id=ctx.workflow_id,
                node_id=ctx.node_id,
                status="completed",
            )

        workflow = WorkflowSpec("wf", [NodeSpec(node_id="n1", next_node=None, action=action)])
        runner = WorkflowRunner(
            store,
            StateMachine(),
            bus,
            workflow=workflow,
            mode=RuntimeMode.dry_run,
            persist_hook=lambda c, r: persisted.append(r),
        )

        runner.execute_node("sdd-1", "n1")
        assert not marker.exists()
        assert persisted == []

    def test_non_dry_run_mutates_and_persists(self, tmp_path: Path) -> None:
        store = _setup(tmp_path)
        bus = store.event_bus("sess-1")
        marker = tmp_path / "mutated.txt"
        persisted: list[NodeResult] = []

        def action(ctx: ExecutionContext) -> NodeResult:
            if not ctx.dry_run:
                marker.write_text("x", encoding="utf-8")
            return NodeResult(
                session_id=ctx.session_id,
                run_id=ctx.run_id,
                workflow_id=ctx.workflow_id,
                node_id=ctx.node_id,
                status="completed",
            )

        workflow = WorkflowSpec("wf", [NodeSpec(node_id="n1", next_node=None, action=action)])
        runner = WorkflowRunner(
            store,
            StateMachine(),
            bus,
            workflow=workflow,
            persist_hook=lambda c, r: persisted.append(r),
        )

        runner.execute_node("sdd-1", "n1")
        assert marker.exists()
        assert len(persisted) == 1
