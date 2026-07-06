"""Dedupe on save: an equal-content live row absorbs the save (MEMORY_CONTRACT rule 6)."""

from __future__ import annotations

from pathlib import Path

from opencontext_memory import MemoryStore, mem_save


def _make_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore.open(tmp_path / "memory.sqlite3")


def _save(store: MemoryStore, *, content: str, project: str | None = "proj"):
    return mem_save(
        store,
        session_id="s-1",
        project=project,
        title="Note",
        content=content,
        type="discovery",
    )


def test_equal_content_returns_existing_id_with_deduplicated_flag(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    first = _save(store, content="the test runner is pytest")
    second = _save(store, content="the test runner is pytest")
    assert second.receipt.id == first.receipt.id
    assert second.receipt.deduplicated is True
    assert first.receipt.deduplicated is False


def test_dedupe_increments_duplicate_count(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    first = _save(store, content="the test runner is pytest")
    _save(store, content="the test runner is pytest")
    with store._connect() as conn:
        row = conn.execute(
            "SELECT duplicate_count FROM observations WHERE id = ?", (first.receipt.id,)
        ).fetchone()
    assert int(row["duplicate_count"]) == 1


def test_different_content_is_not_deduplicated(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    first = _save(store, content="the test runner is pytest")
    second = _save(store, content="the linter is ruff")
    assert second.receipt.id != first.receipt.id
    assert second.receipt.deduplicated is False


def test_dedupe_is_project_scoped(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    first = _save(store, content="the test runner is pytest", project="a")
    second = _save(store, content="the test runner is pytest", project="b")
    assert second.receipt.id != first.receipt.id
    assert second.receipt.deduplicated is False
