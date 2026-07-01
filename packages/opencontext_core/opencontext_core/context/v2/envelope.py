"""Context v2 — PR-010 envelope + budget + routing."""

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


@dataclass
class ContextRanker:
    def rank(self, items: list[dict], query: str) -> list[dict]:
        return sorted(items, key=lambda i: len(i.get("content", "")), reverse=True)


@dataclass
class ContextRouter:
    cache: Any | None = None
    def route(self, envelope: ContextEnvelope) -> ContextEnvelope:
        if self.cache:
            cached = self.cache.get(envelope.task)
            if cached:
                envelope.items = [cached]
        return envelope
