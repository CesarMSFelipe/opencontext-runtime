"""Cache leaf v2 — TTL, LRU, FIFO, Priority strategies. PR-000.3.

doc 58: cache is a leaf — zero imports from KG/Memory/Context/Provider.
doc 60 CONV2 addenda: 4 cache types + invalidation strategies.

LB 2026 — full cache implementation.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any


class CacheStrategy(str, Enum):
    TTL = "ttl"          # time-to-live expiry
    LRU = "lru"          # least recently used eviction
    FIFO = "fifo"        # first-in first-out
    PRIORITY = "priority"  # priority-weighted eviction


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    ttl_seconds: int = 3600
    priority: int = 0
    access_count: int = 0

    @property
    def expired(self) -> bool:
        return (datetime.now(tz=timezone.utc) - self.created_at).total_seconds() > self.ttl_seconds


class SemanticCache:
    """Multi-strategy in-memory cache leaf with eviction policies.

    Supports TTL (default), LRU, FIFO, and priority-weighted eviction.
    ``apply_delta`` invalidates entries matching a set of keys — consumed
    by the KG v2 freshness pipeline (008.e).
    """

    def __init__(self, strategy: CacheStrategy = CacheStrategy.TTL, max_entries: int = 1000) -> None:
        self._strategy = strategy
        self._max_entries = max_entries
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0

    # ── public API ──────────────────────────────────────────────────────

    def get(self, key: str) -> Any:
        entry = self._store.get(key)
        if entry is None or (self._strategy == CacheStrategy.TTL and entry.expired):
            self._misses += 1
            return None
        entry.last_accessed = datetime.now(tz=timezone.utc)
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
            entry.created_at = datetime.now(tz=timezone.utc)
            entry.priority = priority
            return
        if len(self._store) >= self._max_entries:
            self._evict_one()
        self._store[key] = CacheEntry(
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

    # ── introspection ───────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def keys(self) -> list[str]:
        return list(self._store.keys())

    # ── eviction ────────────────────────────────────────────────────────

    def _evict_one(self) -> None:
        if not self._store:
            return
        if self._strategy == CacheStrategy.FIFO:
            self._store.popitem(last=False)
        elif self._strategy == CacheStrategy.LRU:
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


__all__ = ["CacheEntry", "CacheStrategy", "SemanticCache"]
