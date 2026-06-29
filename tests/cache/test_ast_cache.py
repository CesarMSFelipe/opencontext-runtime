"""SC-005 — AST parse-result cache (file-invalidated)."""

from __future__ import annotations

from opencontext_core.cache.ast_cache import AstCache, AstCacheEntry
from opencontext_core.cache.base import CacheType
from opencontext_core.cache.store import CcrBackedCacheStore


def test_ast_entry_type() -> None:
    assert AstCacheEntry(path="a.py").cache_type == CacheType.ast


def test_unchanged_file_hits_without_reparse() -> None:
    store = CcrBackedCacheStore()
    cache = AstCache(store, enabled=True)
    calls = {"n": 0}

    def parse() -> str:
        calls["n"] += 1
        return '{"symbols": ["f"], "edges": []}'

    first, hit1 = cache.get_or_produce("mod.py", "hash_a", parse)
    second, hit2 = cache.get_or_produce("mod.py", "hash_a", parse)

    assert first == second
    assert hit1 is False
    assert hit2 is True
    assert calls["n"] == 1  # the second call did NOT re-parse


def test_changed_hash_misses_and_reparses() -> None:
    store = CcrBackedCacheStore()
    cache = AstCache(store, enabled=True)
    calls = {"n": 0}

    def parse() -> str:
        calls["n"] += 1
        return f"result-{calls['n']}"

    cache.get_or_produce("mod.py", "hash_a", parse)
    _, hit = cache.get_or_produce("mod.py", "hash_b", parse)

    assert hit is False
    assert calls["n"] == 2  # changed content hash -> re-parse


def test_disabled_cache_is_passthrough() -> None:
    store = CcrBackedCacheStore()
    cache = AstCache(store, enabled=False)
    cache.put("mod.py", "hash_a", "body")
    assert cache.get("mod.py", "hash_a") is None
