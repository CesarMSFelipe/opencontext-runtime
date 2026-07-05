"""REQ-cache-v2-001 — MemoryRetrievalCacheEntry keyed by query fingerprint."""

from __future__ import annotations


class TestMemoryRetrievalCache:
    def test_query_fingerprint_deterministic(self) -> None:
        from opencontext_core.cache.v2.memory_retrieval import (
            MemoryRetrievalCacheEntry,
            memory_query_fingerprint,
        )

        fp1 = memory_query_fingerprint("how to add auth", profile="balanced")
        fp2 = memory_query_fingerprint("how to add auth", profile="balanced")
        fp3 = memory_query_fingerprint("how to add auth", profile="low-cost")
        assert fp1 == fp2
        assert fp1 != fp3

        e = MemoryRetrievalCacheEntry(
            key=f"mem_{fp1}",
            value_ref="v_ref_1",
            query_fingerprint=fp1,
            profile="balanced",
        )
        assert e.profile == "balanced"
        assert e.cache_type.value == "memory_retrieval"
