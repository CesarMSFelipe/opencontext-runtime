"""Generic keyed-result cache for KG-query / memory-retrieval (cache types 6 & 7).

Per the design, the KG-query, memory-retrieval, and prompt/context types are
served through the shared ``CacheEntry`` base + a distinguishing ``cache_type``
rather than four more bespoke classes. This single class backs cache types 6
(``kg_query``) and 7 (``memory_retrieval``); prompt/context reuses the existing
``ExactPromptCache``.

Repeated identical queries within a freshness window return the cached result;
provenance ``source_files`` lets the invalidator drop entries on index change.
"""

from __future__ import annotations

from collections.abc import Callable

from opencontext_core.cache.base import CacheEntry, CacheProvenance, CacheType, _hash_text
from opencontext_core.cache.store import CcrBackedCacheStore


class KeyedResultCache:
    """A query-keyed cache over a shared store, parameterized by ``cache_type``."""

    def __init__(
        self,
        store: CcrBackedCacheStore,
        *,
        cache_type: CacheType,
        enabled: bool = False,
    ) -> None:
        self._store = store
        self._cache_type = cache_type
        self.enabled = enabled

    def _key(self, query: str) -> str:
        return _hash_text(f"{self._cache_type}::{query}")

    def get(self, query: str) -> str | None:
        """Return a cached result for ``query`` or ``None`` on a miss."""

        if not self.enabled:
            return None
        return self._store.get_value_typed(self._key(query), str(self._cache_type))

    def put(
        self,
        query: str,
        result: str,
        *,
        source_files: dict[str, str] | None = None,
        source_refs: list[str] | None = None,
        classification: str = "internal",
    ) -> None:
        """Store ``result`` for ``query`` with provenance for invalidation."""

        if not self.enabled:
            return
        entry = CacheEntry(
            key=self._key(query),
            cache_type=self._cache_type,
            value_ref=_hash_text(result),
            provenance=CacheProvenance(
                content_hash=_hash_text(result),
                source_files=source_files or {},
                source_refs=source_refs or [],
            ),
            classification=classification,
        )
        self._store.put(entry, result)

    def get_or_produce(
        self,
        query: str,
        produce: Callable[[], str],
        *,
        source_files: dict[str, str] | None = None,
        source_refs: list[str] | None = None,
        classification: str = "internal",
    ) -> tuple[str, bool]:
        """Return ``(result, was_hit)``; ``produce`` (the re-query) is skipped on a hit."""

        cached = self.get(query)
        if cached is not None:
            return cached, True
        result = produce()
        self.put(
            query,
            result,
            source_files=source_files,
            source_refs=source_refs,
            classification=classification,
        )
        return result, False
