"""SC-012 — default store reuses the CCR backend; cross-run persistence + stats."""

from __future__ import annotations

from opencontext_core.cache.base import CacheType
from opencontext_core.cache.store import CcrBackedCacheStore
from opencontext_core.cache.tool_cache import ToolCache
from opencontext_core.compression.ccr_cache import MemoryCCRBackend, SQLiteCCRBackend


def test_default_store_reuses_ccr_backend() -> None:
    store = CcrBackedCacheStore()
    assert isinstance(store._backend, MemoryCCRBackend)


def test_stats_report_hits_misses_and_by_type() -> None:
    store = CcrBackedCacheStore()
    cache = ToolCache(store, enabled=True)
    cache.get("grep", {"q": "x"})  # miss
    cache.put("grep", {"q": "x"}, "out", mutating=False)
    cache.get("grep", {"q": "x"})  # hit

    stats = store.stats()
    assert stats.hits >= 1
    assert stats.misses >= 1
    by_type = stats.by_type[str(CacheType.tool_output)]
    assert by_type["stored"] >= 1
    assert by_type["hits"] >= 1
    assert by_type["misses"] >= 1


def test_sqlite_entry_survives_fresh_store_open(tmp_path) -> None:
    db = tmp_path / "cache.db"

    store1 = CcrBackedCacheStore(backend=SQLiteCCRBackend(db_path=db, ttl_seconds=3600))
    cache1 = ToolCache(store1, enabled=True)
    cache1.put("grep", {"q": "x"}, "persisted output", mutating=False)

    # Fresh process / fresh store over the same SQLite file, before TTL expiry.
    store2 = CcrBackedCacheStore(backend=SQLiteCCRBackend(db_path=db, ttl_seconds=3600))
    cache2 = ToolCache(store2, enabled=True)
    assert cache2.get("grep", {"q": "x"}) == "persisted output"  # cross-run hit
