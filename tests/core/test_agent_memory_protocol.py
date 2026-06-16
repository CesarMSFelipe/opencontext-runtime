"""Tests for AgentMemoryStore Protocol and NullAgentMemoryStore — 4 cases."""

from __future__ import annotations

from datetime import UTC, datetime

from opencontext_core.memory.agent import AgentMemoryStore, NullAgentMemoryStore
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord


def make_record(record_id: str = "test-id") -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        layer=MemoryLayer.EPISODIC,
        key="test:key",
        content="test content",
        confidence=1.0,
        source_refs=[],
        decay_policy=DecayPolicy(enabled=False),
        tags=[],
        linked_nodes=[],
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )


def test_null_store_satisfies_protocol() -> None:
    store = NullAgentMemoryStore()
    assert isinstance(store, AgentMemoryStore)


def test_null_search_returns_empty() -> None:
    store = NullAgentMemoryStore()
    result = store.search("anything")
    assert result == []


def test_null_write_returns_id() -> None:
    store = NullAgentMemoryStore()
    record = make_record("my-id")
    returned_id = store.write(record)
    assert returned_id == "my-id"


def test_null_failure_boost_returns_empty() -> None:
    store = NullAgentMemoryStore()
    result = store.failure_boost(["SymbolA", "SymbolB"])
    assert result == {}
