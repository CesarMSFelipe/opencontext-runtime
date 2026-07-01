"""Full tests for PR-000.3 cache leaf — all 4 strategies."""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

from opencontext_core.cache.v2 import CacheEntry, CacheStrategy, SemanticCache


class TestTTL:
    def test_get_set(self) -> None:
        c = SemanticCache(CacheStrategy.TTL, max_entries=10)
        c.set("a", 42)
        assert c.get("a") == 42

    def test_expired_ttl(self) -> None:
        c = SemanticCache(CacheStrategy.TTL)
        c.set("a", 1, ttl_seconds=-1)  # already expired
        assert c.get("a") is None

    def test_invalidation(self) -> None:
        c = SemanticCache()
        c.set("a", 1); c.set("b", 2)
        assert c.apply_delta({"a"}) == 1
        assert c.get("a") is None
        assert c.get("b") == 2


class TestLRU:
    def test_lru_eviction(self) -> None:
        c = SemanticCache(CacheStrategy.LRU, max_entries=2)
        c.set("a", 1); c.set("b", 2)
        c.get("a")  # access a, making b least recently used
        c.set("c", 3)  # should evict b
        assert c.get("b") is None
        assert c.get("a") == 1
        assert c.get("c") == 3


class TestFIFO:
    def test_fifo_eviction(self) -> None:
        c = SemanticCache(CacheStrategy.FIFO, max_entries=2)
        c.set("a", 1); c.set("b", 2)
        c.set("c", 3)  # evicts a (first in)
        assert c.get("a") is None
        assert c.get("b") == 2


class TestPriority:
    def test_priority_eviction(self) -> None:
        c = SemanticCache(CacheStrategy.PRIORITY, max_entries=2)
        c.set("a", 1, priority=10); c.set("b", 2, priority=1)
        c.set("c", 3, priority=5)  # evicts b (lowest priority)
        assert c.get("b") is None
        assert c.get("a") == 1


class TestStats:
    def test_hit_rate(self) -> None:
        c = SemanticCache()
        c.set("a", 1)
        c.get("a"); c.get("missing")
        assert c.hit_rate == 0.5

    def test_keys(self) -> None:
        c = SemanticCache()
        c.set("x", 1); c.set("y", 2)
        assert set(c.keys()) == {"x", "y"}
