"""ContextPlanner: converts ContextContract into ContextPlan."""

from __future__ import annotations

from typing import Any

from opencontext_core.models.context_contract import ContextContract
from opencontext_core.models.context_plan import ContextPlan

TIER_BUDGET: dict[str, int] = {"cheap": 8_000, "precise": 16_000, "critical": 28_000}
TIER_RADIUS: dict[str, int] = {"cheap": 1, "precise": 2, "critical": 3}
TIER_ROUNDS: dict[str, int] = {"cheap": 1, "precise": 2, "critical": 3}
TIER_STRATEGY: dict[str, str] = {
    "cheap": "terse",
    "precise": "compact",
    "critical": "none",
}
TIER_MODE: dict[str, str] = {
    "cheap": "fast",
    "precise": "fast",
    "critical": "verified",
}


class ContextPlanner:
    """Converts ContextContract into ContextPlan.

    DIP: depends on protocols for graph and memory (passed as constructor args).
    """

    def __init__(
        self,
        graph: Any = None,
        memory: Any = None,
        semantic_available: bool = False,
    ) -> None:
        self._graph = graph
        self._memory = memory
        self._semantic_available = semantic_available

    def plan(self, contract: ContextContract) -> ContextPlan:
        tier = contract.risk_tier
        mode = TIER_MODE.get(tier, "fast")
        budget = TIER_BUDGET.get(tier, 16_000)
        radius = TIER_RADIUS.get(tier, 2)
        rounds = TIER_ROUNDS.get(tier, 2)
        strategy = TIER_STRATEGY.get(tier, "compact")
        include_memory = self._memory is not None
        include_semantic = self._semantic_available

        return ContextPlan(
            mode=mode,  # type: ignore[arg-type]
            tier=tier,
            budget_tokens=budget,
            must_read=list(contract.required_files),
            should_read=[],
            must_verify=list(contract.must_verify),
            include_tests=contract.task_type not in ("documentation", "configuration"),
            include_memory=include_memory,
            include_semantic=include_semantic,
            compression_strategy=strategy,  # type: ignore[arg-type]
            graph_radius=radius,
            expansion_rounds=rounds,
            memory_query=contract.task,
        )
