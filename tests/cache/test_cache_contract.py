"""Cache Contract v1 guard (doc 59 §Internal contract versioning)."""

from __future__ import annotations

from opencontext_core.cache.base import CACHE_CONTRACT_VERSION, CacheEntry, CacheType


def test_cache_contract_version_is_one() -> None:
    assert CACHE_CONTRACT_VERSION == 1


def test_entry_carries_contract_version() -> None:
    entry = CacheEntry(cache_type=CacheType.semantic, key="k")
    assert entry.contract_version == CACHE_CONTRACT_VERSION
