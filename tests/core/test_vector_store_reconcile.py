"""LocalVectorStore must reconcile to the freshly-scanned file set on re-index.

Regression: re-indexing enqueued embeddings for the current files but never removed
vectors for files that are no longer scanned (a since-deleted file, or a vendored
tree now excluded by ignore rules, e.g. a venv). Those orphaned vectors kept
surfacing as semantic retrieval evidence (e.g. ``oc-audit-venv/.../debugging.py``).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from opencontext_core.compat import UTC
from opencontext_core.embeddings.models import EmbeddedItem
from opencontext_core.embeddings.stores import LocalVectorStore
from opencontext_core.models.context import DataClassification


def _item(item_id: str, source_path: str, project: str = "demo") -> EmbeddedItem:
    return EmbeddedItem(
        id=f"emb_{item_id}",
        item_id=item_id,
        item_type="file",
        project_name=project,
        content="x",
        vector=[1.0, 0.0, 0.0],
        classification=DataClassification.INTERNAL,
        created_at=datetime.now(tz=UTC),
        embedded_at=datetime.now(tz=UTC),
        metadata={"source_path": source_path},
    )


def test_prune_absent_sources_removes_unscanned_files(tmp_path: Path) -> None:
    store = LocalVectorStore(tmp_path)
    store.store(
        [
            _item("file:src/keep.py", "src/keep.py"),
            _item("symbol:src/keep.py:Foo", "src/keep.py"),
            _item("file:oc-audit-venv/dep.py", "oc-audit-venv/dep.py"),
            _item("file:src/gone.py", "src/gone.py"),
        ]
    )

    removed = store.prune_absent_sources({"src/keep.py"}, project_name="demo")

    assert removed == 2
    remaining = {meta.metadata.get("source_path") for meta in store._metadata.values()}
    assert remaining == {"src/keep.py"}

    # Survives a reload from disk (the rewrite was persisted, not just in-memory).
    reloaded = LocalVectorStore(tmp_path)
    paths = {meta.metadata.get("source_path") for meta in reloaded._metadata.values()}
    assert paths == {"src/keep.py"}


def test_prune_absent_sources_scopes_to_project(tmp_path: Path) -> None:
    store = LocalVectorStore(tmp_path)
    store.store(
        [
            _item("file:a.py", "a.py", project="demo"),
            _item("file:other.py", "other.py", project="other"),
        ]
    )

    # Only 'demo' is reconciled; the other project's vectors must be untouched even
    # though 'other.py' is not in the keep-set for 'demo'.
    removed = store.prune_absent_sources({"a.py"}, project_name="demo")

    assert removed == 0
    paths = {meta.metadata.get("source_path") for meta in store._metadata.values()}
    assert paths == {"a.py", "other.py"}


def test_prune_absent_sources_noop_when_nothing_stale(tmp_path: Path) -> None:
    store = LocalVectorStore(tmp_path)
    store.store([_item("file:a.py", "a.py")])
    assert store.prune_absent_sources({"a.py"}, project_name="demo") == 0


def test_create_id_is_deterministic_per_source_item() -> None:
    """Re-embedding the same source must reuse the storage id (upsert), not mint a
    fresh one. A timestamp in the id made every re-index a new record, growing the
    store unbounded (1.9GB / 60k lines for a 6k-node project)."""
    a = EmbeddedItem.create(
        item_id="symbol:foo", item_type="symbol", project_name="demo", content="x"
    )
    b = EmbeddedItem.create(
        item_id="symbol:foo", item_type="symbol", project_name="demo", content="x changed later"
    )
    assert a.id == b.id == "emb_symbol:foo"


def test_reindex_same_source_does_not_duplicate_on_disk(tmp_path: Path) -> None:
    """Two index passes of the same file leave one record in memory AND one line on
    disk: store() appends, but a fresh load compacts the duplicate id away."""
    store = LocalVectorStore(tmp_path)
    store.store([_item("file:a.py", "a.py")])
    store.store([_item("file:a.py", "a.py")])  # second pass: same id -> overwrite
    assert len(store._metadata) == 1

    index = tmp_path / "embeddings" / "index.jsonl"
    assert len([ln for ln in index.read_text().splitlines() if ln.strip()]) == 2  # appended

    reloaded = LocalVectorStore(tmp_path)  # _load() compacts on the way in
    assert len(reloaded._metadata) == 1
    assert len([ln for ln in index.read_text().splitlines() if ln.strip()]) == 1
