"""Context v2 ranking — CONV2 #9 (BM25 + recency, 4th layer)."""

from __future__ import annotations

from typing import Any


class ContextRanker:
    """BM25-style overlap + recency ranker. ponytail: score = bm25 * recency."""

    def rank(self, items: list[dict], query: str) -> list[dict]:
        scored = [(self._score(item, query), item) for item in items]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

    def _score(self, item: dict, query: str) -> float:
        content = item.get("content", "")
        recency = item.get("recency", 0.5)  # ponytail: default 0.5 if missing
        return self._bm25_sim(content, query) * float(recency)

    def _bm25_sim(self, content: str, query: str) -> float:
        if not query or not content:
            return 0.0
        q_terms = set(query.lower().split())
        c_lower = content.lower()
        hits = sum(1 for t in q_terms if t in c_lower)
        return hits / max(1, len(q_terms))


# ponytail: API compat with legacy envelope.py
__all__ = ["ContextRanker"]
# mark unused import as intentional
_ = Any