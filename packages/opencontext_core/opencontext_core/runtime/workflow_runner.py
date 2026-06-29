"""WorkflowRunner and the 14-step node execution pipeline (SPEC RC-008/010).

The runner drives one run over a workflow-neutral ``WorkflowSpec`` (an ordered
list of ``NodeSpec``). ``execute_node`` runs the standard 14-step pipeline from
``02-runtime-architecture.md`` §12. Step 9 (execute node action) runs the
node's action callable, or delegates to ``HarnessRunner`` when none is given;
steps 11-12 (persist artifacts / emit receipts) are pluggable hooks that default
to no-ops (durable stores are deferred to PR-002).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from opencontext_core.runtime.brain import RuntimeBrainPort
from opencontext_core.runtime.decisions import DecisionLog, RuntimeDecision
from opencontext_core.runtime.event_bus import EventBus
from opencontext_core.runtime.events import make_event
from opencontext_core.runtime.modes import RuntimeMode
from opencontext_core.runtime.run import GateResult, NextAction, NodeResult, RunResult
from opencontext_core.runtime.session import LiveState
from opencontext_core.runtime.session_store import SessionStore
from opencontext_core.runtime.state_machine import StateMachine


@dataclass
class ExecutionContext:
    """Inputs handed to a node action during step 9 of the pipeline."""

    session_id: str
    run_id: str
    workflow_id: str
    node_id: str
    mode: RuntimeMode
    dry_run: bool
    bus: EventBus
    runtime_context: dict[str, Any] = field(default_factory=dict)


# A node action receives the execution context and returns a NodeResult.
NodeAction = Callable[[ExecutionContext], NodeResult]


@dataclass
class NodeSpec:
    """A single workflow node definition (workflow-neutral)."""

    node_id: str
    required_capabilities: list[str] = field(default_factory=list)
    required_gates: list[str] = field(default_factory=list)
    next_node: str | None = None
    action: NodeAction | None = None


@dataclass
class WorkflowSpec:
    """An ordered, workflow-neutral node graph for one workflow id."""

    workflow_id: str
    nodes: list[NodeSpec]

    def first(self) -> NodeSpec:
        return self.nodes[0]

    def get(self, node_id: str) -> NodeSpec | None:
        return next((n for n in self.nodes if n.node_id == node_id), None)


def _noop_hook(ctx: ExecutionContext, result: NodeResult) -> None:
    """Default persist/receipt hook: does nothing (PR-002 lands durable stores)."""


class WorkflowRunner:
    """Executes one workflow run via the 14-step node pipeline."""

    def __init__(
        self,
        store: SessionStore,
        state_machine: StateMachine,
        bus: EventBus,
        *,
        workflow: WorkflowSpec,
        mode: RuntimeMode = RuntimeMode.run_to_completion,
        harness_runner: Any = None,
        persist_hook: Callable[[ExecutionContext, NodeResult], None] = _noop_hook,
        receipt_hook: Callable[[ExecutionContext, NodeResult], None] = _noop_hook,
        brain: RuntimeBrainPort | None = None,
        brain_enabled: bool = False,
    ) -> None:
        self._store = store
        self._state_machine = state_machine
        self._bus = bus
        self._workflow = workflow
        self._mode = mode
        self._harness_runner = harness_runner
        self._persist_hook = persist_hook
        self._receipt_hook = receipt_hook
        # Advisory Runtime Brain (PR-000.1). Default off: when disabled the
        # runner behaves exactly as PR-001 and writes no decisions. When on, the
        # Brain only *records* a recommendation — the State Machine below still
        # governs every transition (RB-007/RB-008).
        self._brain = brain
        self._brain_enabled = brain_enabled and brain is not None

    # ----------------------------------------------------------- public API
    def run_to_completion(self, run_id: str) -> RunResult:
        """Step through the run until it completes, fails, or pauses."""
        run = self._store.load_run(self._session_id_for(run_id), run_id)
        if run.current_node is None:
            run.current_node = self._workflow.first().node_id
            self._store.save_run(run)
        node_results: list[NodeResult] = []
        status = "completed"
        # Hard cap as a safety net against a malformed (cyclic) workflow so the
        # loop can never run away; the no-progress break below is the normal exit.
        max_steps = max(len(self._workflow.nodes) * 2 + 1, 2)
        for _ in range(max_steps):
            node_id = run.current_node
            if node_id is None:
                break
            result = self.execute_node(run_id, node_id)
            node_results.append(result)
            if result.status == "failed":
                status = "failed"
                break
            run = self._store.load_run(self._session_id_for(run_id), run_id)
            if run.current_node is None:
                status = "completed"
                break
            if run.current_node == node_id:
                # No progress (blocked / awaiting) — stop rather than spin.
                status = run.status
                break
        return RunResult(run_id=run_id, status=status, node_results=node_results)

    def step(self, run_id: str) -> NextAction:
        """Execute the current node and report the next action."""
        run = self._store.load_run(self._session_id_for(run_id), run_id)
        node_id = run.current_node or self._workflow.first().node_id
        result = self.execute_node(run_id, node_id)
        if result.status == "failed":
            return NextAction(kind="fail", node_id=node_id, reason=result.error or "node failed")
        if result.next_recommended:
            return NextAction(kind="execute_node", node_id=result.next_recommended)
        return NextAction(kind="complete", reason="no further nodes")

    def execute_node(self, run_id: str, node_id: str) -> NodeResult:
        """Run the standard 14-step node pipeline (book §12)."""
        started = time.monotonic()
        # Step 1: load session.
        session_id = self._session_id_for(run_id)
        session = self._store.load_session(session_id)
        run = self._store.load_run(session_id, run_id)

        # Step 2: load workflow + node definition.
        node = self._workflow.get(node_id)
        if node is None:
            return self._fail(
                session_id, run_id, node_id, error="workflow_not_found: unknown node"
            )

        ctx = ExecutionContext(
            session_id=session_id,
            run_id=run_id,
            workflow_id=self._workflow.workflow_id,
            node_id=node_id,
            mode=self._mode,
            dry_run=self._mode is RuntimeMode.dry_run,
            bus=self._bus,
            runtime_context={"gates": {}},
        )

        # Step 3: check capabilities.
        available = {k for k, v in session.capability_snapshot.items() if v}
        available |= {k for k, v in session.capabilities.items() if v}
        missing = [c for c in node.required_capabilities if c not in available]
        if missing:
            self._bus.publish(
                make_event(
                    session_id=session_id,
                    run_id=run_id,
                    workflow_id=ctx.workflow_id,
                    node_id=node_id,
                    type="node.capability_missing",
                    status="failed",
                    message=f"missing required capabilities: {', '.join(missing)}",
                    metadata={"missing_capabilities": missing},
                )
            )
            from opencontext_core.runtime.errors import RuntimeErrorCode

            return self._fail(
                session_id,
                run_id,
                node_id,
                error=f"{RuntimeErrorCode.CAPABILITY_MISSING}: {', '.join(missing)}",
                duration_ms=self._elapsed_ms(started),
            )

        # Steps 4-8: policy / context / persona / skills / harness pre-checks.
        # PR-001 extension points; default permissive no-ops.

        # Step 9: execute node action (delegates to HarnessRunner when absent).
        try:
            if node.action is not None:
                result = node.action(ctx)
            elif self._harness_runner is not None and not ctx.dry_run:
                legacy = self._harness_runner.run(ctx.workflow_id, session.task)
                result = NodeResult(
                    session_id=session_id,
                    run_id=run_id,
                    workflow_id=ctx.workflow_id,
                    node_id=node_id,
                    status="completed",
                    summary=f"harness run {getattr(legacy, 'run_id', '')}",
                )
            else:
                result = NodeResult(
                    session_id=session_id,
                    run_id=run_id,
                    workflow_id=ctx.workflow_id,
                    node_id=node_id,
                    status="completed",
                    summary="no-op node",
                )
        except Exception as exc:
            result = self._fail(
                session_id, run_id, node_id, error=str(exc), duration_ms=self._elapsed_ms(started)
            )

        # Step 10: validate output contract (extension point; default pass).

        # Steps 11-12: persist artifacts / emit receipts — pluggable hooks.
        # dry_run performs no persistence (RC-011).
        if not ctx.dry_run and result.status != "failed":
            self._persist_hook(ctx, result)
            self._receipt_hook(ctx, result)

        # Step 13: harness post-checks (extension point; default no-op).

        # Step 14: transition.
        if result.status == "failed":
            run.status = "failed"
            run.completed_at = result_now()
        elif node.next_node is None:
            # Terminal node: completion needs no transition decision. A missing
            # successor means "done", which is distinct from a blocked transition.
            result.next_recommended = None
            run.current_node = None
            run.status = "completed"
            run.completed_at = result_now()
            result.duration_ms = result.duration_ms or self._elapsed_ms(started)
        else:
            # Non-terminal node: the State Machine governs the transition.
            decision = self._state_machine.evaluate(
                current_node=node_id,
                target_node=node.next_node,
                transition_condition={"required_gates": node.required_gates},
                runtime_context=ctx.runtime_context,
            )
            result.gates = [
                GateResult(gate=g, passed=g not in decision.failed_gates)
                for g in decision.required_gates
            ]
            # Advisory Brain seam (PR-000.1): record WHY this transition went the
            # way it did. Default off → no decision writes, behaviour unchanged.
            # The State Machine decision above is authoritative; the Brain only
            # recommends and the recommendation is recorded (governed_by set when
            # the State Machine diverges — no silent override, RB-008).
            if self._brain_enabled:
                self._record_transition_decision(run, node, decision, ctx)
            if decision.allowed:
                result.next_recommended = decision.next_node
                run.current_node = decision.next_node
                run.status = "running"
            else:
                # Transition blocked (e.g. an unmet gate): stay put and wait.
                result.next_recommended = None
                run.current_node = node_id
                run.status = "blocked"
            result.duration_ms = result.duration_ms or self._elapsed_ms(started)

        self._store.save_run(run)

        # Emit a node event and update live state.
        event = self._bus.publish(
            make_event(
                session_id=session_id,
                run_id=run_id,
                workflow_id=ctx.workflow_id,
                node_id=node_id,
                type=f"node.{result.status}",
                status=result.status,
                message=result.summary or result.error or "",
            )
        )
        self._store.write_live_state(
            LiveState(
                session_id=session_id,
                run_id=run_id,
                workflow=ctx.workflow_id,
                node=run.current_node,
                status=run.status,
                message=result.summary or result.error or "",
                last_event_id=event.event_id,
            )
        )
        return result

    # --------------------------------------------------- decision-log seam
    def _record_transition_decision(
        self,
        run: Any,
        node: NodeSpec,
        transition: Any,
        ctx: ExecutionContext,
    ) -> None:
        """Record the Brain's advisory next-node recommendation for this step.

        Advisory only: the ``transition`` (a State Machine ``TransitionDecision``)
        is authoritative. When the State Machine diverges from the Brain's
        recommendation, ``governed_by`` is stamped so the override is logged,
        never silent (RB-008). Defensive: any Brain error degrades to a no-op so
        the deterministic core can never be destabilised by an advisor.
        """
        if self._brain is None:
            return
        try:
            recommendation = self._brain.recommend(
                run_id=run.run_id,
                runtime_context={
                    "current_node": node.node_id,
                    "proposed_node": node.next_node,
                    "run_id": run.run_id,
                    "session_id": run.session_id,
                    "node_id": node.node_id,
                    "gates": dict(ctx.runtime_context.get("gates", {})),
                },
            )
        except Exception:
            return
        if recommendation is None:
            return
        proposed = recommendation.chosen or None
        if not transition.allowed or transition.next_node != proposed:
            recommendation.governed_by = "state_machine"
            recommendation.reason = (
                f"{recommendation.reason} | governed_by=state_machine: {transition.reason}"
            )
        run.decision_log.append(recommendation)

    def append_decision(self, run_id: str, decision: RuntimeDecision) -> RuntimeDecision:
        """Attach a decision entry to the run's :class:`DecisionLog` (RC-CONV)."""
        session_id = self._session_id_for(run_id)
        run = self._store.load_run(session_id, run_id)
        run.decision_log.append(decision)
        self._store.save_run(run)
        return decision

    def decisions(self, run_id: str) -> DecisionLog:
        """Read back the run's decision log."""
        run = self._store.load_run(self._session_id_for(run_id), run_id)
        return run.decision_log

    # ----------------------------------------------------------- internals
    def _session_id_for(self, run_id: str) -> str:
        """Map a run id to its owning session id.

        Run ids are minted as ``<workflow>-<hex>`` inside a session; the
        ``RuntimeApi`` records the binding via the session's ``active_run_id``.
        We resolve by scanning session run folders, which keeps the runner
        decoupled from how ids are minted.
        """
        for session_dir in sorted(self._store.sessions_path.glob("*")):
            if (session_dir / "runs" / run_id / "run.json").exists():
                return session_dir.name
        raise FileNotFoundError(run_id)

    def _fail(
        self,
        session_id: str,
        run_id: str,
        node_id: str,
        *,
        error: str,
        duration_ms: int = 0,
    ) -> NodeResult:
        return NodeResult(
            session_id=session_id,
            run_id=run_id,
            workflow_id=self._workflow.workflow_id,
            node_id=node_id,
            status="failed",
            error=error,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.monotonic() - started) * 1000)


def result_now() -> str:
    from datetime import datetime

    from opencontext_core.compat import UTC

    return datetime.now(tz=UTC).isoformat()
