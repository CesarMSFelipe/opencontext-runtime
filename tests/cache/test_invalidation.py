"""SC-009 — cache invalidation rules + file-change wiring."""

from __future__ import annotations

from opencontext_core.cache.ast_cache import AstCache
from opencontext_core.cache.invalidation import CacheInvalidationRule, CacheInvalidator
from opencontext_core.cache.store import CcrBackedCacheStore
from opencontext_core.indexing.file_watcher import FileWatcher


def _seed(store: CcrBackedCacheStore) -> AstCache:
    cache = AstCache(store, enabled=True)
    cache.put("a.py", "h1", "result-a")  # provenance.source_files = {"a.py": "h1"}
    cache.put("b.py", "h2", "result-b")
    return cache


def test_file_change_invalidates_dependent_entries() -> None:
    store = CcrBackedCacheStore()
    cache = _seed(store)
    invalidator = CacheInvalidator(store)

    removed = invalidator.on_file_change("a.py", "modified")

    assert removed == 1
    assert cache.get("a.py", "h1") is None  # invalidated
    assert cache.get("b.py", "h2") == "result-b"  # untouched


def test_non_referencing_change_removes_nothing() -> None:
    store = CcrBackedCacheStore()
    _seed(store)
    invalidator = CacheInvalidator(store)
    assert invalidator.on_file_change("unrelated.py", "modified") == 0


def test_rule_path_glob_scopes_invalidation() -> None:
    store = CcrBackedCacheStore()
    cache = _seed(store)
    rule = CacheInvalidationRule(name="src-only", match_paths=["b.*"])
    invalidator = CacheInvalidator(store, rules=[rule])

    assert invalidator.on_file_change("a.py", "modified") == 0  # not matched by glob
    assert invalidator.on_file_change("b.py", "modified") == 1
    assert cache.get("b.py", "h2") is None


def test_filewatcher_add_callback_composes(tmp_path) -> None:
    store = CcrBackedCacheStore()
    cache = _seed(store)
    invalidator = CacheInvalidator(store)

    base_calls: list[str] = []
    watcher = FileWatcher(
        tmp_path, callback=lambda rel, change: base_calls.append(rel), use_watchdog=False
    )
    watcher.add_callback(invalidator.as_callback())

    # Simulate a watcher dispatch.
    watcher.callback("a.py", "modified")

    assert base_calls == ["a.py"]  # original callback still fired
    assert cache.get("a.py", "h1") is None  # invalidator also fired
