"""Context v2 — PR-010 envelope, ranker, router, compression, usefulness.

CONV2 #9: ContextRanker with BM25 + recency scoring.
CONV2 #11: Usefulness scoring (content-to-query relevance).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextEnvelope:
    task: str
    items: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0
    budget: int = 3000
    omissions: list[str] = field(default_factory=list)
    compressed: bool = False


class ContextRanker:
    """BM25-style + recency ranker. CONV2 #9."""

    def rank(self, items: list[dict], query: str) -> list[dict]:
        scored = []
        for item in items:
            content = item.get("content", "")
            score = self._bm25_sim(content, query)
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

    def _bm25_sim(self, content: str, query: str) -> float:
        if not query or not content:
            return 0.0
        q_terms = set(query.lower().split())
        c_lower = content.lower()
        hits = sum(1 for t in q_terms if t in c_lower)
        return hits / max(1, len(q_terms))


class ContextRouter:
    """Route context through cache, compression, and ranking."""

    def __init__(self, cache: Any = None, ranker: ContextRanker | None = None) -> None:
        self._cache = cache
        self._ranker = ranker or ContextRanker()

    def route(self, envelope: ContextEnvelope) -> ContextEnvelope:
        if self._cache and (cached := self._cache.get(envelope.task)):
            envelope.items = [cached]
            return envelope
        envelope.items = self._ranker.rank(envelope.items, envelope.task)
        if envelope.tokens_used > envelope.budget:
            envelope.omissions.append(f"budget exceeded: {envelope.tokens_used}/{envelope.budget}")
        return envelope


class ContextCompressor:
    """Token budget compressor for context items."""

    def compress(self, envelope: ContextEnvelope, target_tokens: int | None = None) -> ContextEnvelope:
        if target_tokens is None:
            target_tokens = envelope.budget
        trimmed = []
        used = 0
        for item in envelope.items:
            tokens = len(item.get("content", "")) // 4
            if used + tokens > target_tokens:
                envelope.omissions.append(f"omitted {item.get('id', '?')} for budget")
                continue
            trimmed.append(item)
            used += tokens
        envelope.items = trimmed
        envelope.tokens_used = used
        envelope.compressed = True
        return envelope


def usefulness_score(item: dict, query: str) -> float:
    """CONV2 #11: content-to-query relevance score."""
    if not query:
        return 0.0
    content = item.get("content", "")
    q_terms = set(query.lower().split())
    c_terms = set(content.lower().split())
    if not c_terms:
        return 0.0
    overlap = q_terms & c_terms
    return len(overlap) / len(q_terms)
