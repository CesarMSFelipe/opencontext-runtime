"""`mem_compact` consolidates duplicates; `mem_purge` removes all managed state.

MEMORY_CONTRACT: compaction preserves pinned records (MEM-005/006); purge is the
uninstall-grade removal of everything managed (MEM-008).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from opencontext_memory import (
    MemoryStore,
    Observation,
    mem_compact,
    mem_purge,
    mem_search,
)
from opencontext_memory.tools.mem_get_observation import MemoryNotFound, mem_get_observation


def _make_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore.open(tmp_path / "memory.sqlite3")


def _write(store: MemoryStore, *, content: str, project: str = "proj", pinned: bool = False) -> int:
    return store.write(
        Observation(
            session_id="s-1",
            title="Note",
            content=content,
            project=project,
            type="discovery",
            pinned=pinned,
        )
    )


def test_compact_reports_before_after_and_compacted_ids(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    keeper = _write(store, content="dup content")
    dup = _write(store, content="dup content")
    _write(store, content="unique content")
    report = mem_compact(store)
    assert report["before"] == 3
    assert report["after"] == 2
    assert report["compacted_ids"] == [dup]
    # The oldest duplicate survives; the compacted one is gone from reads.
    assert mem_get_observation(store, observation_id=keeper)["id"] == keeper
    with pytest.raises(MemoryNotFound):
        mem_get_observation(store, observation_id=dup)


def test_compact_marks_compacted_lifecycle_state(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _write(store, content="dup content")
    dup = _write(store, content="dup content")
    mem_compact(store)
    with store._connect() as conn:
        row = conn.execute(
            "SELECT lifecycle_state, deleted_at FROM observations WHERE id = ?", (dup,)
        ).fetchone()
    assert row["lifecycle_state"] == "compacted"
    assert row["deleted_at"] is not None


def test_compact_never_touches_pinned(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _write(store, content="dup content")
    pinned_dup = _write(store, content="dup content", pinned=True)
    report = mem_compact(store)
    assert pinned_dup not in report["compacted_ids"]
    assert mem_get_observation(store, observation_id=pinned_dup)["deleted_at"] is None


def test_compact_noop_reports_zero_compacted(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _write(store, content="only content")
    report = mem_compact(store)
    assert report["before"] == 1
    assert report["after"] == 1
    assert report["compacted_ids"] == []


def test_purge_removes_all_observations(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    one = _write(store, content="first")
    _write(store, content="second")
    report = mem_purge(store)
    assert report["purged"] is True
    assert report["observations_removed"] == 2
    with pytest.raises(MemoryNotFound):
        mem_get_observation(store, observation_id=one)
    assert mem_search(store, query="first") == []


def test_purge_on_empty_store_is_idempotent(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    report = mem_purge(store)
    assert report["purged"] is True
    assert report["observations_removed"] == 0
