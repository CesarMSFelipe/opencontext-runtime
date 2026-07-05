"""Cache leaf v2 — public exports (PR-016 / SPEC §3.2 cache).

Re-exports the unified typed-cache primitives from ``cache.base`` (book
doc 58, doc 59) plus the L4 strategy-aware in-memory cache used by the
existing tests. The cache is a leaf: zero imports from KG / Memory /
Context / Provider — enforced by ``leaf_guard`` + ``tests/cache/v2/test_leaf.py``.
"""

from __future__ import annotations

__capability__ = "cache.v2"

from opencontext_core.cache.base import (
    CACHE_CONTRACT_VERSION,
    CacheEntry,
    CacheProvenance,
    CacheStats,
    CacheStore,
    CacheType,
    cache_entry_id,
)
from opencontext_core.cache.v2.registry import CacheRegistry

# Re-export the strategy-aware in-memory cache (existing surface).
from opencontext_core.cache.v2.strategies import CacheStrategy, SemanticCache

CacheProvider = CacheStore  # canonical Protocol name used by the v2 namespace.

__all__ = [
    "CACHE_CONTRACT_VERSION",
    "CacheEntry",
    "CacheProvenance",
    "CacheProvider",
    "CacheRegistry",
    "CacheStats",
    "CacheStore",
    "CacheStrategy",
    "CacheType",
    "SemanticCache",
    "cache_entry_id",
]
