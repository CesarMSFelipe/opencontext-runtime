"""Cache leaf — L7 zero-import isolation layer. PR-000.3.

doc 58: cache is a leaf — zero imports from KG/Memory/Context/Provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    ttl_seconds: int = 3600

    @property
    def expired(self) -> bool:
        return (datetime.now(tz=timezone.utc) - self.created_at).total_seconds() > self.ttl_seconds


class SemanticCache:
    """In-memory TTL cache with invalidation hooks. Zero upward imports."""

    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Any:
        entry = self._store.get(key)
        if entry is None or entry.expired:
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        self._store[key] = CacheEntry(key=key, value=value, ttl_seconds=ttl_seconds)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def apply_delta(self, deleted_keys: set[str]) -> int:
        count = 0
        for k in deleted_keys:
            if k in self._store:
                self._store.pop(k)
                count += 1
        return count


__all__ = ["CacheEntry", "SemanticCache"]
