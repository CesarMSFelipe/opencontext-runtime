"""Tests for LocalMemoryStore — 10 cases."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from opencontext_core.memory.agent import AgentMemoryStore, NullAgentMemoryStore
from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord
from opencontext_core.models.evidence import EvidenceRef


def make_record(
    record_id: str = "rec-1",
    key: str = "test:key",
    content: str = "some content",
    layer: MemoryLayer = MemoryLayer.EPISODIC,
    confidence: float = 0.9,
    created_at: datetime | None = None,
) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    ts = created_at or now
    return MemoryRecord(
        id=record_id,
        layer=layer,
        key=key,
        content=content,
        confidence=confidence,
        source_refs=[],
        decay_policy=DecayPolicy(enabled=False),
        tags=[],
        linked_nodes=[],
        created_at=ts,
        updated_at=ts,
    )


@pytest.fixture()
def store() -> LocalMemoryStore:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield LocalMemoryStore(Path(tmpdir) / "mem.db")


def test_store_and_search(store: LocalMemoryStore) -> None:
    record = make_record(content="auth middleware crash failure")
    store.write(record)
    results = store.search("auth middleware")
    assert any(r.id == record.id for r in results)


def test_failure_layer_boost(store: LocalMemoryStore) -> None:
    record = make_record(
        record_id="fail-1",
        content="ContextPackBuilder",
        layer=MemoryLayer.FAILURE,
    )
    store.write(record)
    boosts = store.failure_boost(["ContextPackBuilder"])
    assert boosts["ContextPackBuilder"] > 0.0


def test_reinforce_increases_confidence(store: LocalMemoryStore) -> None:
    record = make_record(record_id="reinf-1", confidence=0.7)
    store.write(record)
    evidence = EvidenceRef(source="test", source_type="code", confidence=1.0)
    store.reinforce("reinf-1", evidence)
    results = store.search(record.content)
    assert any(r.id == "reinf-1" for r in results)
    # Re-fetch via key

    backend = store._backend
    recs = backend.get_by_key(record.key)
    updated = next((r for r in recs if r.id == "reinf-1"), None)
    assert updated is not None
    assert updated.confidence > 0.7


def test_contradict_decreases_confidence(store: LocalMemoryStore) -> None:
    record = make_record(record_id="contra-1", confidence=0.8)
    store.write(record)
    evidence = EvidenceRef(source="counter-evidence", source_type="code", confidence=1.0)
    store.contradict("contra-1", evidence)
    backend = store._backend
    recs = backend.get_by_key(record.key)
    updated = next((r for r in recs if r.id == "contra-1"), None)
    assert updated is not None
    assert updated.confidence < 0.8


def test_decay_prunes_only_old_and_low_confidence(store: LocalMemoryStore) -> None:
    """decay() deletes records that are BOTH stale (>90d) and low-confidence
    (<0.3); everything failing either condition must survive."""
    old = datetime.now(tz=UTC) - timedelta(days=120)
    recent = datetime.now(tz=UTC) - timedelta(days=1)

    store.write(make_record("stale-weak", key="k:a", confidence=0.2, created_at=old))  # pruned
    store.write(make_record("stale-strong", key="k:b", confidence=0.9, created_at=old))  # kept
    store.write(make_record("fresh-weak", key="k:c", confidence=0.2, created_at=recent))  # kept

    pruned = store.decay()

    assert pruned == 1
    survivors = {
        r.id
        for key in ("k:a", "k:b", "k:c")
        for r in store._backend.get_by_key(key)
    }
    assert survivors == {"stale-strong", "fresh-weak"}  # only stale+weak removed


def test_null_agent_memory_store_satisfies_protocol() -> None:
    null_store = NullAgentMemoryStore()
    assert isinstance(null_store, AgentMemoryStore)


def test_search_with_scope_filter(store: LocalMemoryStore) -> None:
    store.write(make_record(record_id="ep", layer=MemoryLayer.EPISODIC, content="graph db failure"))
    store.write(
        make_record(record_id="pr", layer=MemoryLayer.PROCEDURAL, content="graph db failure")
    )
    results = store.search("graph db failure", scope=MemoryLayer.EPISODIC)
    assert all(r.layer == MemoryLayer.EPISODIC for r in results)


def test_failure_boost_returns_zero_for_unknown_symbol(store: LocalMemoryStore) -> None:
    boosts = store.failure_boost(["totally_unknown_symbol_xyz"])
    assert boosts["totally_unknown_symbol_xyz"] == 0.0


def test_write_returns_id(store: LocalMemoryStore) -> None:
    record = make_record(record_id="id-check")
    returned = store.write(record)
    assert returned == "id-check"


def test_search_empty_db_returns_empty(store: LocalMemoryStore) -> None:
    results = store.search("anything at all")
    assert results == []
