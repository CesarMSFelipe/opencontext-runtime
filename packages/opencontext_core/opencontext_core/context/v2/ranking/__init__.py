"""Context v2 ranking — BM25 + recency (CONV2 #9) and L4 usefulness (CONV2 #10).

Public re-exports preserve the legacy ``from .ranking import ContextRanker``
path used by envelope.py and the v2 tests.
"""

from __future__ import annotations

from typing import Any

from opencontext_core.context.v2.ranking.score import (
    DEFAULT_WEIGHTS,
    LAYER_WEIGHTS,
    UsefulnessScore,
    UsefulnessWeights,
    usefulness,
)


class ContextRanker:
    """BM25-style overlap + recency ranker. ponytail: score = bm25 * recency."""

    def rank(self, items: list[dict[Any, Any]], query: str) -> list[dict[Any, Any]]:
        scored = [(self._score(item, query), item) for item in items]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

    def _score(self, item: dict[Any, Any], query: str) -> float:
        content = item.get("content", "")
        recency = item.get("recency", 0.5)  # NOTE: default 0.5 if missing
        return self._bm25_sim(content, query) * float(recency)

    def _bm25_sim(self, content: str, query: str) -> float:
        if not query or not content:
            return 0.0
        q_terms = set(query.lower().split())
        c_lower = content.lower()
        hits = sum(1 for t in q_terms if t in c_lower)
        return hits / max(1, len(q_terms))


__all__ = [
    "DEFAULT_WEIGHTS",
    "LAYER_WEIGHTS",
    "ContextRanker",
    "UsefulnessScore",
    "UsefulnessWeights",
    "usefulness",
]
_ = Any