"""Context planner agent — builds ContextContract using v2 runtime."""
from __future__ import annotations

from typing import Any

from opencontext_core.agents.base import BaseAgent
from opencontext_core.context.planning.classifier import TaskClassifier
from opencontext_core.context.planning.contract import ContextContractBuilder
from opencontext_core.context.planning.planner import ContextPlanner
from opencontext_core.context.planning.risk import RiskClassifier


class ContextPlannerAgent(BaseAgent):
    """Builds a verified ContextContract for a task. Pure local, no LLM."""

    async def execute(self) -> dict[str, Any]:
        task = self.config.objectives[0] if self.config.objectives else ""
        contract = ContextContractBuilder(
            classifier=TaskClassifier(),
            risk_classifier=RiskClassifier(),
        ).build(task)
        plan = ContextPlanner().plan(contract)
        return {
            "contract": contract.model_dump(),
            "plan": plan.model_dump(),
            "task_type": contract.task_type,
            "risk_tier": contract.risk_tier,
            "token_budget": contract.token_budget,
            "must_verify": [g.id for g in contract.must_verify],
        }
