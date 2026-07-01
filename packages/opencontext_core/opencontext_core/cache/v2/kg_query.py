"""Cache v2 — `KgQueryCacheEntry` keyed by `kg_<hash>` (PR-008 consumes)."""

from __future__ import annotations

import hashlib

from opencontext_core.cache.base import CacheEntry, CacheType


def kg_query_key(*, query: str, kg_version: str) -> str:
    """Deterministic key: ``sha256(kg_version + query)``."""
    payload = f"{kg_version}\x00{query}".encode()
    digest = hashlib.sha256(payload).hexdigest()
    return f"kg_{digest[:24]}"


class KgQueryCacheEntry(CacheEntry):
    """KG-query cache entry keyed by query + kg_version fingerprint (REQ-cache-v2-001)."""

    cache_type: CacheType = CacheType.kg_query
    kg_version: str = ""
    query_fingerprint: str = ""

    @classmethod
    def build(cls, *, query: str, kg_version: str, value_ref: str) -> KgQueryCacheEntry:
        return cls(
            key=kg_query_key(query=query, kg_version=kg_version),
            value_ref=value_ref,
            kg_version=kg_version,
            query_fingerprint=hashlib.sha256(query.encode("utf-8")).hexdigest()[:24],
        )


__all__ = ["KgQueryCacheEntry", "kg_query_key"]