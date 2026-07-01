"""Cache v2 strategy-aware in-memory cache (PR-000.3).

Holds the ``SemanticCache`` + ``CacheStrategy`` enum that already ship in
``cache/v2/__init__.py`` pre-PR-000.3 — moved here so the leaf public
surface (``cache/v2/__init__``) can stay focused on typed-entry plumbing.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class CacheStrategy(str, Enum):
    TTL = "ttl"
    LRU = "lru"
    FIFO = "fifo"
    PRIORITY = "priority"


@dataclass
class _StrategyEntry:
    key: str
    value: Any
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    ttl_seconds: int = 3600
    priority: int = 0
    access_count: int = 0

    @property
    def expired(self) -> bool:
        return (datetime.now(tz=UTC) - self.created_at).total_seconds() > self.ttl_seconds


# Re-use the existing dataclass name ``CacheEntry`` from v2.__init__ for the
# strategy store; the typed Pydantic CacheEntry lives in cache.base. Both
# coexist because they serve different layers (runtime vs typed).
CacheEntry = _StrategyEntry  # type: ignore[misc,assignment]


class SemanticCache:
    """Multi-strategy in-memory cache leaf with eviction policies."""

    def __init__(self, strategy: CacheStrategy = CacheStrategy.TTL, max_entries: int = 1000) -> None:
        self._strategy = strategy
        self._max_entries = max_entries
        self._store: OrderedDict[str, _StrategyEntry] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0

    def get(self, key: str) -> Any:
        entry = self._store.get(key)
        if entry is None or (self._strategy == CacheStrategy.TTL and entry.expired):
            self._misses += 1
            return None
        entry.last_accessed = datetime.now(tz=UTC)
        entry.access_count += 1
        self._hits += 1
        if self._strategy == CacheStrategy.LRU:
            self._store.move_to_end(key)
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int = 3600, priority: int = 0) -> None:
        if key in self._store:
            entry = self._store[key]
            entry.value = value
            entry.ttl_seconds = ttl_seconds
            entry.created_at = datetime.now(tz=UTC)
            entry.priority = priority
            return
        if len(self._store) >= self._max_entries:
            self._evict_one()
        self._store[key] = _StrategyEntry(
            key=key, value=value, ttl_seconds=ttl_seconds, priority=priority
        )

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def apply_delta(self, deleted_keys: set[str]) -> int:
        count = 0
        for k in deleted_keys:
            if k in self._store:
                self._store.pop(k)
                count += 1
        return count

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def keys(self) -> list[str]:
        return list(self._store.keys())

    def _evict_one(self) -> None:
        if not self._store:
            return
        if self._strategy in (CacheStrategy.FIFO, CacheStrategy.LRU):
            self._store.popitem(last=False)
        elif self._strategy == CacheStrategy.PRIORITY:
            lowest = min(self._store.values(), key=lambda e: (e.priority, e.access_count))
            self._store.pop(lowest.key, None)
        else:  # TTL
            for k, e in list(self._store.items()):
                if e.expired:
                    self._store.pop(k)
                    return
            self._store.popitem(last=False)


__all__ = ["CacheStrategy", "SemanticCache"]