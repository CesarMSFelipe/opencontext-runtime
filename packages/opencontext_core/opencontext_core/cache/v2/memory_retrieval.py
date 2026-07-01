"""Cache v2 — `MemoryRetrievalCacheEntry` keyed by query fingerprint."""

from __future__ import annotations

import hashlib

from opencontext_core.cache.base import CacheEntry, CacheType


def memory_query_fingerprint(query: str, *, profile: str) -> str:
    """Deterministic fingerprint: ``sha256(profile + query)``."""
    payload = f"{profile}\x00{query}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


class MemoryRetrievalCacheEntry(CacheEntry):
    """Memory-retrieval cache entry keyed by query fingerprint (REQ-cache-v2-001)."""

    cache_type: CacheType = CacheType.memory_retrieval
    query_fingerprint: str = ""
    profile: str = ""

    @classmethod
    def build(
        cls, *, query: str, profile: str, value_ref: str
    ) -> "MemoryRetrievalCacheEntry":
        fp = memory_query_fingerprint(query, profile=profile)
        return cls(
            key=f"mem_{fp}",
            value_ref=value_ref,
            query_fingerprint=fp,
            profile=profile,
        )


__all__ = ["MemoryRetrievalCacheEntry", "memory_query_fingerprint"]