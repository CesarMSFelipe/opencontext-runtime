"""SC-006 / SC-007 — local provider-response cache + KV-prefix reuse."""

from __future__ import annotations

from opencontext_core.cache.provider_cache import ProviderCacheEntry, ProviderResponseCache
from opencontext_core.cache.store import CcrBackedCacheStore
from opencontext_core.compression.cache_aligner import CacheAligner


def _call(cache: ProviderResponseCache, produce, *, context: str = "ctx") -> tuple[str, bool]:
    return cache.get_or_produce(
        provider="mock",
        model="m",
        prompt_version="v1",
        user_input="hello",
        context=context,
        produce=produce,
        system_prompt="SYS PROMPT stable",
    )


def test_identical_request_served_without_provider_call() -> None:
    store = CcrBackedCacheStore()
    cache = ProviderResponseCache(store, enabled=True, aligner=CacheAligner())
    calls = {"n": 0}

    def produce() -> str:
        calls["n"] += 1
        return "provider response"

    out1, hit1 = _call(cache, produce)
    out2, hit2 = _call(cache, produce)

    assert out1 == out2 == "provider response"
    assert hit1 is False
    assert hit2 is True
    assert calls["n"] == 1  # provider invoked once


def test_provider_entry_carries_prefix_hash_from_aligner() -> None:
    store = CcrBackedCacheStore()
    cache = ProviderResponseCache(store, enabled=True, aligner=CacheAligner())
    cache.put(
        provider="mock",
        model="m",
        prompt_version="v1",
        user_input="hello",
        context="ctx",
        response="r",
        system_prompt="SYS PROMPT stable",
    )
    key = ProviderResponseCache._key("mock", "m", "v1", _h("hello"), _h("ctx"))
    entry = store._index[key]
    assert isinstance(entry, ProviderCacheEntry)
    assert entry.prefix_hash is not None


def test_aligner_stable_prefix_drives_cache_hint() -> None:
    aligner = CacheAligner()
    # Byte-identical stable prefixes across two turns -> matching hash + hint.
    first = aligner.align("SYS PROMPT stable", "same payload")
    second = aligner.align("SYS PROMPT stable", "same payload")
    assert first.prefix_hash == second.prefix_hash
    assert second.is_cacheable is True


def test_disabled_provider_cache_passthrough() -> None:
    store = CcrBackedCacheStore()
    cache = ProviderResponseCache(store, enabled=False)
    cache.put(
        provider="mock",
        model="m",
        prompt_version="v1",
        user_input="hello",
        context="ctx",
        response="r",
    )
    assert (
        cache.get(
            provider="mock", model="m", prompt_version="v1", user_input="hello", context="ctx"
        )
        is None
    )


def _h(text: str) -> str:
    from opencontext_core.cache.base import _hash_text

    return _hash_text(text)
