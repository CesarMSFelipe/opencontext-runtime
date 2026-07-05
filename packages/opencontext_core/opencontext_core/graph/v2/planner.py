"""KG v2 planner — budget-enforced query planning.

PR-008.c: ContextQueryPlanner enforces a token budget ceiling and
produces a KgQueryPlan that downstream retrievers consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class BudgetExceededError(Exception):
    """Raised when a plan would exceed the token budget."""


@dataclass(frozen=True)
class KgQueryPlan:
    query: str
    node_types: list[str] = field(default_factory=list)
    edge_types: list[str] = field(default_factory=list)
    max_tokens: int = 3000
    limit: int = 50


class ContextQueryPlanner:
    """Plan a KG query within a token budget.

    Rejects plans that would exceed the ceiling and emits a
    BudgetExceededError so the caller can fall back to a lighter
    retrieval surface.
    """

    def __init__(self, ceiling: int = 3000) -> None:
        self._ceiling = ceiling

    def plan(self, query: str, node_types: list[str] | None = None) -> KgQueryPlan:
        if self._estimate_tokens(query) > self._ceiling:
            raise BudgetExceededError(
                f"Estimated {self._estimate_tokens(query)} tokens exceeds ceiling {self._ceiling}"
            )
        return KgQueryPlan(
            query=query,
            node_types=node_types or [],
            max_tokens=self._ceiling,
        )

    def _estimate_tokens(self, text: str) -> int:
        # NOTE: ~4 chars per token heuristic
        return max(1, len(text) // 4)


__all__ = ["BudgetExceededError", "ContextQueryPlanner", "KgQueryPlan"]
