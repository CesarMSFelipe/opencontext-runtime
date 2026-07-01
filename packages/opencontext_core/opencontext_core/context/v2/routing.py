"""Context v2 routing — cache lookup → ranker fallback."""

from __future__ import annotations

from typing import Any, Protocol

from opencontext_core.context.v2.envelope import ContextEnvelope
from opencontext_core.context.v2.ranking import ContextRanker


class _CacheLike(Protocol):
    def get(self, key: str) -> Any: ...


class ContextRouter:
    """Route envelope through cache; on miss rank items via ContextRanker."""

    def __init__(self, cache: _CacheLike | None = None, ranker: ContextRanker | None = None) -> None:
        self._cache = cache
        self._ranker = ranker or ContextRanker()

    def route(self, envelope: ContextEnvelope) -> ContextEnvelope:
        if self._cache is not None:
            cached = self._cache.get(envelope.task)
            if cached is not None:
                envelope.items = [cached]
                return envelope
        envelope.items = self._ranker.rank(envelope.items, envelope.task)
        if envelope.tokens_used > envelope.budget:
            envelope.omissions.append(
                f"budget exceeded: {envelope.tokens_used}/{envelope.budget}"
            )
        return envelope


__all__ = ["ContextRouter"]