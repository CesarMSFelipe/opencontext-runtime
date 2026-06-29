"""Schedulers (PR-001 phase-ordering seam + PR-000.1 advisory next-node).

Two distinct schedulers live here:

* :class:`Scheduler` / :class:`HarnessScheduler` — the PR-001 phase-ordering
  seam: ``schedule(workflow, harness_runner) -> list[str]`` defers to the
  legacy ``HarnessRunner.schedule_phases`` so phase order is preserved.

* :class:`RuntimeScheduler` — the PR-000.1 advisory Scheduler API (doc 59):
  ``decide_next(state) -> NextNodeDecision`` and ``simulate(plan) ->
  SimulationReport``. It turns the Brain's ``next_node`` recommendation into a
  :class:`SchedulingDecision` and hands it to the deterministic State Machine,
  which makes the authoritative ``TransitionDecision`` (RB-004/RB-007). The
  Scheduler never mutates run state.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from opencontext_core.runtime.brain import RuntimeBrain
from opencontext_core.runtime.decisions import (
    DecisionKind,
    NextNodeDecision,
    SchedulingDecision,
    SimulationReport,
)
from opencontext_core.runtime.state_machine import StateMachine, TransitionDecision


@runtime_checkable
class Scheduler(Protocol):
    """Resolves the execution order of a workflow's phases/nodes."""

    def schedule(self, workflow: str, *, harness_runner: Any) -> list[str]: ...


@runtime_checkable
class PlanCostEstimator(Protocol):
    """Real plan-cost estimator port (PR-011 Runtime Intelligence seam).

    The Scheduler (lower layer) defines this port; the upper Runtime Intelligence
    layer supplies a concrete implementation (``runtime_intelligence.simulator``),
    so ``simulate()`` can be wired to a real estimator without the runtime
    depending on the intelligence layer (doc 58 dependency direction).
    """

    name: str

    def estimate_plan(self, plan: Mapping[str, Any]) -> tuple[int, float, int]:
        """Return ``(estimated_tokens, estimated_cost, estimated_duration_ms)``."""
        ...


class HarnessScheduler:
    """Default scheduler: defer to ``HarnessRunner.schedule_phases``."""

    def schedule(self, workflow: str, *, harness_runner: Any) -> list[str]:
        # Delegating preserves the legacy DAG/track ordering exactly.
        return list(harness_runner.schedule_phases(workflow))


class RuntimeScheduler:
    """Advisory next-node scheduler (Scheduler API, doc 59).

    Wraps the Brain's ``next_node`` recommendation; the State Machine governs.
    """

    def __init__(
        self,
        brain: RuntimeBrain,
        *,
        state_machine: StateMachine | None = None,
        estimator: PlanCostEstimator | None = None,
    ) -> None:
        self.brain = brain
        self.state_machine = state_machine or StateMachine()
        # Optional real plan-cost estimator (PR-011). When None, ``simulate``
        # returns the typed stub forecast (the seam stays stable either way).
        self.estimator = estimator

    def decide_next(self, state: Mapping[str, Any]) -> NextNodeDecision:
        """Return the Brain-recommended next node (advisory)."""
        decision = self.brain.decide(DecisionKind.next_node, state)
        return NextNodeDecision(
            current_node=state.get("current_node"),
            proposed_node=decision.chosen or None,
            reason=decision.reason,
            confidence=decision.confidence,
        )

    def schedule(self, run_id: str, context: Mapping[str, Any]) -> SchedulingDecision:
        """Produce a :class:`SchedulingDecision` for *run_id* (advisory only)."""
        decision = self.brain.decide(DecisionKind.next_node, {**context, "run_id": run_id})
        next_node = NextNodeDecision(
            current_node=context.get("current_node"),
            proposed_node=decision.chosen or None,
            reason=decision.reason,
            confidence=decision.confidence,
        )
        return SchedulingDecision(run_id=run_id, next_node=next_node, decision=decision)

    def govern(
        self,
        scheduling: SchedulingDecision,
        *,
        required_gates: list[str] | None = None,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> tuple[SchedulingDecision, TransitionDecision]:
        """Hand a scheduling proposal to the State Machine for governance.

        The returned :class:`TransitionDecision` is authoritative. When the
        recommendation is rejected (or altered), ``decision.governed_by`` is set
        to ``"state_machine"`` and the reason recorded — never a silent override
        (RB-007/RB-008). This call does not mutate any run.
        """
        next_node = scheduling.next_node
        transition = self.state_machine.evaluate(
            current_node=next_node.current_node,
            target_node=next_node.proposed_node,
            transition_condition={"required_gates": list(required_gates or [])},
            runtime_context=runtime_context,
        )
        overridden = (not transition.allowed) or (transition.next_node != next_node.proposed_node)
        if overridden:
            scheduling.decision.governed_by = "state_machine"
            scheduling.decision.reason = (
                f"{scheduling.decision.reason} | governed_by=state_machine: {transition.reason}"
            )
        return scheduling, transition

    def simulate(self, plan: Mapping[str, Any]) -> SimulationReport:
        """Dry-run forecast a plan.

        When a real :class:`PlanCostEstimator` was injected (PR-011 Runtime
        Intelligence), use it to fill estimated tokens/cost/duration; otherwise
        return the typed stub forecast. Either way the seam is stable.
        """
        nodes = [str(node) for node in plan.get("nodes", [])]
        if self.estimator is not None:
            tokens, cost, duration_ms = self.estimator.estimate_plan(plan)
            return SimulationReport(
                run_id=plan.get("run_id"),
                proposed_path=nodes,
                estimated_tokens=tokens,
                estimated_cost=cost,
                estimated_duration_ms=duration_ms,
                estimator=self.estimator.name,
                notes=["estimated by runtime_intelligence cost model (provider-free)"],
            )
        return SimulationReport(
            run_id=plan.get("run_id"),
            proposed_path=nodes,
            estimator="stub",
            notes=[
                "stub estimator: inject a PlanCostEstimator (PR-011 Runtime "
                "Intelligence) for real cost/confidence forecasts; the seam is typed",
            ],
        )
