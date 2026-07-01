"""Cache v2 — `SemanticCacheEntry` (hash-by-embedding)."""

from __future__ import annotations

import hashlib
import json

from opencontext_core.cache.base import CacheEntry, CacheType


def key_by_embedding(text: str, *, producer: str) -> str:
    """Deterministic cache key from embedding text + producer.

    Producers (KG / Memory / Context / Provider) carry the embedding
    surface; the cache leaf only sees opaque bytes + a producer id so
    collisions across producers are impossible.
    """
    payload = {"producer": producer, "text": text}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SemanticCacheEntry(CacheEntry):
    """Semantic-cache entry, keyed by embedding hash + producer."""

    cache_type: CacheType = CacheType.semantic
    embedding_hash: str = ""


__all__ = ["SemanticCacheEntry", "key_by_embedding"]