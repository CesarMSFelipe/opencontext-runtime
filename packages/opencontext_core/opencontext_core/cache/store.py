"""Default cross-run :class:`CacheStore` backed by the CCR content store.

This reuses the proven content-addressed TTL+stats backend from
``compression/ccr_cache.py`` (``MemoryCCRBackend`` / ``SQLiteCCRBackend``)
rather than introducing a new persistent store. Bodies are stored
content-addressed and redacted on write; classification gates the write
(fail closed for ``secret`` / ``regulated``).

Importing ``compression`` (an L4 sibling) is allowed — the leaf-utility rule
only forbids the cache from importing KG / Memory / Context / Provider.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from opencontext_core.cache.base import (
    CacheEntry,
    CacheStats,
    cache_allowed_for_classifications,
)
from opencontext_core.compression.ccr_cache import (
    CCRCacheBackend,
    CCREntry,
    MemoryCCRBackend,
)
from opencontext_core.safety.redaction import SinkGuard


class CcrBackedCacheStore:
    """A :class:`~opencontext_core.cache.base.CacheStore` over a CCR backend.

    The CCR backend owns persistence, TTL, capacity eviction, and hit/miss
    counters. A small in-process index of entry provenance is kept so
    ``invalidate_paths`` can drop entries whose source files changed; the index
    is rebuilt as entries are read, so cross-run reads still hit while
    cross-run path-invalidation falls back to TTL + re-index (honest partial).
    """

    def __init__(
        self,
        *,
        backend: CCRCacheBackend | None = None,
        ttl_seconds: int = 3600,
    ) -> None:
        self._backend = backend or MemoryCCRBackend(ttl_seconds=ttl_seconds)
        self._ttl = ttl_seconds
        self._index: dict[str, CacheEntry] = {}
        self._by_type: dict[str, dict[str, int]] = {}

    def _bump(self, cache_type: str, field: str) -> None:
        bucket = self._by_type.setdefault(cache_type, {"stored": 0, "hits": 0, "misses": 0})
        bucket[field] = bucket.get(field, 0) + 1

    def put(self, entry: CacheEntry, body: str) -> None:
        """Store ``entry`` + ``body`` — gated by classification, redacted on write."""

        if not cache_allowed_for_classifications((entry.classification,)):
            return
        safe_body, _ = SinkGuard().redact(body)
        now = datetime.now(tz=UTC)
        stored_at = entry.created_at or now.isoformat()
        expires_at = entry.expires_at or (now + timedelta(seconds=self._ttl)).isoformat()
        record = json.dumps({"entry": entry.model_dump(mode="json"), "body": safe_body})
        self._backend.put(
            CCREntry(
                content_hash=entry.key,
                content_type=str(entry.cache_type),
                original=record,
                compressed="",
                stored_at=stored_at,
                expires_at=expires_at,
            )
        )
        self._index[entry.key] = entry
        self._bump(str(entry.cache_type), "stored")

    def _read(self, key: str) -> tuple[CacheEntry, str] | None:
        ccr = self._backend.get(key)  # bumps backend hit/miss counters
        if ccr is None:
            return None
        data = json.loads(ccr.original)
        # Project the persisted dump onto the base fields: a typed entry's
        # subclass-only fields are not needed to return the body, and the base
        # model is ``extra="forbid"``. The original typed object stays in
        # ``_index`` for provenance/invalidation.
        base_only = {k: v for k, v in data["entry"].items() if k in CacheEntry.model_fields}
        entry = CacheEntry.model_validate(base_only)
        self._index.setdefault(key, entry)
        self._bump(str(entry.cache_type), "hits")
        return entry, data["body"]

    def get(self, key: str) -> CacheEntry | None:
        """Return the cached entry for ``key`` or ``None``."""

        read = self._read(key)
        return read[0] if read else None

    def get_value(self, key: str) -> str | None:
        """Return the cached (redacted) body for ``key`` or ``None``.

        This is the recompute-avoidance surface the typed caches use.
        """

        read = self._read(key)
        return read[1] if read else None

    def get_value_typed(self, key: str, cache_type: str) -> str | None:
        """Like :meth:`get_value` but records a per-type miss on a miss.

        Hits are recorded in :meth:`_read`; this records the miss so
        ``stats().by_type`` carries a real hit/miss ratio per cache type for the
        Runtime Optimizer to read.
        """

        read = self._read(key)
        if read is None:
            self._bump(cache_type, "misses")
            return None
        return read[1]

    def invalidate_paths(self, paths: list[str], *, cache_types: list[str] | None = None) -> int:
        """Drop every entry whose provenance references any of ``paths``.

        ``cache_types`` (optional) narrows invalidation to those cache types;
        ``None`` (the default) invalidates matching entries of any type.
        """

        targets = set(paths)
        type_filter = set(cache_types) if cache_types else None
        removed = 0
        for key, entry in list(self._index.items()):
            if type_filter is not None and str(entry.cache_type) not in type_filter:
                continue
            if targets & set(entry.provenance.source_files):
                self._backend.remove(key)
                del self._index[key]
                removed += 1
        return removed

    def stats(self) -> CacheStats:
        """Return aggregate hit/miss telemetry (PR-011 surface)."""

        backend_stats = self._backend.stats()
        return CacheStats(
            entries=backend_stats.entries,
            hits=backend_stats.hits,
            misses=backend_stats.misses,
            evictions=backend_stats.evictions,
            by_type={k: dict(v) for k, v in self._by_type.items()},
        )
