"""SC-008 / SC-002 — KG-query + memory-retrieval (base+cache_type) and prompt reuse."""

from __future__ import annotations

from opencontext_core.cache.base import CacheType, build_cache_key
from opencontext_core.cache.exact import ExactPromptCache
from opencontext_core.cache.keyed import KeyedResultCache
from opencontext_core.cache.store import CcrBackedCacheStore


def test_repeated_kg_query_served_from_cache() -> None:
    store = CcrBackedCacheStore()
    cache = KeyedResultCache(store, cache_type=CacheType.kg_query, enabled=True)
    calls = {"n": 0}

    def query() -> str:
        calls["n"] += 1
        return "kg result"

    cache.get_or_produce("who calls foo", query, source_files={"foo.py": "h"})
    out, hit = cache.get_or_produce("who calls foo", query, source_files={"foo.py": "h"})

    assert out == "kg result"
    assert hit is True
    assert calls["n"] == 1
    assert store.stats().by_type[str(CacheType.kg_query)]["hits"] >= 1


def test_memory_retrieval_uses_same_base() -> None:
    store = CcrBackedCacheStore()
    cache = KeyedResultCache(store, cache_type=CacheType.memory_retrieval, enabled=True)
    cache.put("recent decisions", "memory result")
    assert cache.get("recent decisions") == "memory result"


def test_prompt_context_reuses_exact_prompt_cache() -> None:
    cache = ExactPromptCache()
    key = build_cache_key(
        workflow_name="wf",
        project_hash="ph",
        model_name="m",
        prompt_version="v1",
        user_input="hi",
        context="ctx",
    )
    cache.set(key, "assembled prompt")
    assert cache.get(key) == "assembled prompt"
