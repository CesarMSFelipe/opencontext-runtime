"""Tests for context.v2.routing — cache + ranker routing."""

from __future__ import annotations

from opencontext_core.context.v2.envelope import ContextEnvelope
from opencontext_core.context.v2.routing import ContextRouter


class _FakeCache:
    def __init__(self, payload: object | None = None) -> None:
        self._payload = payload
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> object | None:
        if self._payload is None:
            self.misses += 1
            return None
        self.hits += 1
        return self._payload


def test_router_cache_hit_skips_ranking() -> None:
    cached = {"id": "cached", "content": "prior answer"}
    cache = _FakeCache(payload=cached)
    router = ContextRouter(cache=cache)
    env = ContextEnvelope(task="task", items=[{"id": "x", "content": "fresh"}])
    out = router.route(env)
    assert out.items == [cached]
    assert cache.hits == 1
    assert cache.misses == 0


def test_router_cache_miss_ranks_items() -> None:
    cache = _FakeCache(payload=None)
    router = ContextRouter(cache=cache)
    env = ContextEnvelope(task="auth", items=[
        {"id": "a", "content": "auth"},
        {"id": "b", "content": "weather"},
    ])
    out = router.route(env)
    assert out.items[0]["id"] == "a"
    assert cache.misses == 1


def test_router_no_cache_just_ranks() -> None:
    router = ContextRouter(cache=None)
    env = ContextEnvelope(task="auth", items=[{"id": "a", "content": "auth"}])
    out = router.route(env)
    assert out.items == [{"id": "a", "content": "auth"}]