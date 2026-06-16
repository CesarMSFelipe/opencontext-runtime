"""Tests for SQLiteMemoryBackend — 6 cases."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opencontext_core.memory.backends import SQLiteMemoryBackend
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord


def make_record(
    record_id: str = "rec-1",
    key: str = "test:key",
    content: str = "some test content",
    layer: MemoryLayer = MemoryLayer.EPISODIC,
) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=record_id,
        layer=layer,
        key=key,
        content=content,
        confidence=0.9,
        source_refs=[],
        decay_policy=DecayPolicy(enabled=False),
        tags=["test"],
        linked_nodes=[],
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def backend() -> SQLiteMemoryBackend:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield SQLiteMemoryBackend(Path(tmpdir) / "mem.db")


def test_store_and_search_round_trip(backend: SQLiteMemoryBackend) -> None:
    record = make_record(content="auth middleware failure")
    backend.store(record)
    results = backend.search("auth middleware")
    assert any(r.id == record.id for r in results)


def test_layer_filter(backend: SQLiteMemoryBackend) -> None:
    backend.store(
        make_record(record_id="ep", layer=MemoryLayer.EPISODIC, content="episodic memory")
    )
    backend.store(
        make_record(record_id="pr", layer=MemoryLayer.PROCEDURAL, content="episodic memory")
    )
    results = backend.search("episodic memory", layer=MemoryLayer.EPISODIC)
    assert all(r.layer == MemoryLayer.EPISODIC for r in results)


def test_fts5_finds_content(backend: SQLiteMemoryBackend) -> None:
    backend.store(make_record(content="knowledge graph indexing failure pattern"))
    results = backend.search("knowledge graph")
    assert len(results) >= 1


def test_get_by_key(backend: SQLiteMemoryBackend) -> None:
    record = make_record(key="procedural:auth_changes")
    backend.store(record)
    results = backend.get_by_key("procedural:auth_changes")
    assert any(r.id == record.id for r in results)


def test_delete(backend: SQLiteMemoryBackend) -> None:
    record = make_record(record_id="to-delete")
    backend.store(record)
    backend.delete("to-delete")
    results = backend.get_by_key(record.key)
    assert not any(r.id == "to-delete" for r in results)


def test_empty_search_returns_empty(backend: SQLiteMemoryBackend) -> None:
    results = backend.search("   ")
    assert results == []


def test_recall_for_non_adjacent_terms(backend: SQLiteMemoryBackend) -> None:
    """Query terms need not be adjacent in the stored content.

    A rigid single-phrase MATCH would miss this: "auth failure" is not a
    contiguous substring of "auth middleware crash failure".
    """
    backend.store(make_record(content="auth middleware crash failure trace"))
    results = backend.search("auth failure")
    assert len(results) >= 1


def test_recall_for_punctuated_natural_language_query(backend: SQLiteMemoryBackend) -> None:
    """A natural-language question with punctuation still recalls the record."""
    backend.store(make_record(content="the auth middleware validates tokens"))
    results = backend.search("How does the auth middleware work?")
    assert len(results) >= 1


def test_search_with_only_punctuation_returns_empty(backend: SQLiteMemoryBackend) -> None:
    """No usable tokens -> no match, never an FTS5 syntax error."""
    backend.store(make_record(content="anything"))
    assert backend.search("?? -- !!") == []
