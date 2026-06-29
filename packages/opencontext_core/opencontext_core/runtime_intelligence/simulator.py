"""Runtime Simulator (book §10) — deterministic, provider-free cognitive dry run.

Predicts execution before running using ONLY local signals: the deterministic
:class:`~opencontext_core.context.planning.classifier.TaskClassifier`, the
:class:`~opencontext_core.context.planning.risk.RiskClassifier`, the
:class:`~opencontext_core.runtime_intelligence.cost.CostEngine`, and (optionally) a
local KG search callable. It makes ZERO provider calls (invariant §23; the report
asserts ``provider_calls == 0``).

This module also supplies :class:`SchedulerPlanEstimator`, the concrete
implementation of the PR-000.1 ``runtime/scheduler.py:PlanCostEstimator`` port, so
``RuntimeScheduler.simulate()`` can be wired to a real estimator (the upper
intelligence layer implements the port the lower runtime layer declares).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from opencontext_core.context.planning.classifier import TaskClassifier
from opencontext_core.context.planning.risk import RiskClassifier
from opencontext_core.context.planning.workflow_selector import select_workflow
from opencontext_core.models.intelligence import SimulationReport
from opencontext_core.runtime_intelligence import events as ri_events
from opencontext_core.runtime_intelligence import telemetry_layout
from opencontext_core.runtime_intelligence.cost import CostEngine

# Retrieval tier (RiskClassifier) → execution lane.
_TIER_TO_LANE = {"cheap": "quick", "precise": "fast", "critical": "full"}


class RuntimeSimulator:
    """Provider-free dry run → :class:`SimulationReport` (book §10)."""

    def __init__(
        self,
        *,
        classifier: TaskClassifier | None = None,
        risk_classifier: RiskClassifier | None = None,
        cost_engine: CostEngine | None = None,
        kg_search: Callable[[str], tuple[list[str], list[str]]] | None = None,
    ) -> None:
        self._classifier = classifier or TaskClassifier()
        self._risk = risk_classifier or RiskClassifier()
        self._cost = cost_engine or CostEngine(classifier=self._classifier)
        # Optional local-only KG lookup → (expected_files, expected_symbols).
        self._kg_search = kg_search

    def simulate(
        self,
        task: str,
        *,
        root: str | Path = ".",
        emit: bool = False,
    ) -> SimulationReport:
        """Predict workflow/lane/files/risks/cost/confidence — no provider calls."""
        classification = self._classifier.classify(task)
        tier = self._risk.classify(classification.task_type, classification.risk_level)
        lane = _TIER_TO_LANE.get(tier, "fast")

        # Workflow selection goes through the ONE shared selector so `simulate` and
        # `run --workflow auto` cannot disagree (B6 / AVH-013).
        workflow = select_workflow(
            task, classifier=self._classifier, risk=self._risk
        ).workflow

        expected_files: list[str] = []
        expected_symbols: list[str] = []
        if self._kg_search is not None:
            expected_files, expected_symbols = self._kg_search(task)

        risk_flags = self._risk_flags(classification)
        estimate = self._cost.estimate(task, workflow, lane, root=root)
        recommendation = (
            f"run '{workflow}' on the '{lane}' lane "
            f"(task_type={classification.task_type}, risk={classification.risk_level})"
        )

        report = SimulationReport(
            task=task[:200],
            recommended_workflow=workflow,
            recommended_lane=lane,
            expected_files=list(expected_files),
            expected_symbols=list(expected_symbols),
            expected_tests=[],
            risk_flags=risk_flags,
            cost_estimates=[estimate],
            confidence_estimate=round(classification.confidence, 3),
            recommendation=recommendation,
            provider_calls=0,  # invariant: the simulator never calls a provider.
        )
        if emit:
            telemetry_layout.append_event(
                ri_events.SIMULATION_CREATED,
                {
                    "task": task[:120],
                    "recommended_workflow": workflow,
                    "recommended_lane": lane,
                },
                root,
            )
        return report

    @staticmethod
    def _risk_flags(classification: Any) -> list[str]:
        flags: list[str] = []
        if classification.risk_level in ("high", "critical"):
            flags.append(f"risk:{classification.risk_level}")
        if classification.requires_mutation:
            flags.append("requires_mutation")
        if classification.task_type == "security":
            flags.append("security_sensitive")
        return flags


class SchedulerPlanEstimator:
    """Concrete ``PlanCostEstimator`` for ``RuntimeScheduler.simulate()`` (PR-011).

    Provider-free. Estimates a plan's cost from the plan's ``task`` (via the Cost
    Engine) when present, else from the node count. Satisfies the structural
    ``runtime/scheduler.py:PlanCostEstimator`` protocol.
    """

    name = "runtime_intelligence"

    # Rough per-node budget when the plan carries no task text.
    _TOKENS_PER_NODE = 1500
    _MS_PER_NODE = 5000

    def __init__(self, *, cost_engine: CostEngine | None = None) -> None:
        self._cost = cost_engine or CostEngine()

    def estimate_plan(self, plan: Mapping[str, Any]) -> tuple[int, float, int]:
        task = str(plan.get("task", "") or "")
        nodes = list(plan.get("nodes", []) or [])
        if task:
            workflow = str(plan.get("workflow", "oc-flow") or "oc-flow")
            lane = str(plan.get("lane", "fast") or "fast")
            estimate = self._cost.estimate(task, workflow, lane)
            tokens = estimate.estimated_input_tokens + estimate.estimated_output_tokens
            duration_ms = estimate.estimated_duration_s * 1000
            return tokens, 0.0, duration_ms
        count = max(len(nodes), 1)
        return count * self._TOKENS_PER_NODE, 0.0, count * self._MS_PER_NODE


__all__ = ["RuntimeSimulator", "SchedulerPlanEstimator"]
