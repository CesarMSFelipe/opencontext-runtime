"""PR-009 SPEC-MEM-009-14: budgeted, ordered memory retrieval + memory.retrieved event."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opencontext_core.memory.events import MemoryEvent, MemoryEventEmitter
from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.memory.retrieval import (
    estimate_tokens,
    node_budget,
    query_for_node,
    retrieve_memory,
)
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord
from opencontext_core.models.memory import MemoryQuery


def _rec(store: LocalMemoryStore, rid: str, layer: MemoryLayer, content: str) -> None:
    now = datetime.now(tz=UTC)
    store.write(
        MemoryRecord(
            id=rid,
            layer=layer,
            key=f"{layer.value}:{rid}",
            content=content,
            confidence=0.9,
            decay_policy=DecayPolicy(enabled=False),
            created_at=now,
            updated_at=now,
        )
    )


@pytest.fixture()
def store() -> LocalMemoryStore:
    with tempfile.TemporaryDirectory() as tmp:
        yield LocalMemoryStore(Path(tmp) / "mem.db")


def test_node_budget_table() -> None:
    assert node_budget("oc-flow", "gather_context") == (8, 2000)
    # Unknown node falls back to the default budget.
    assert node_budget("oc-flow", "unknown-node") == (8, 2000)


def test_retrieval_respects_node_token_budget(store: LocalMemoryStore) -> None:
    big = "alpha " * 600  # ~3600 chars -> ~900 tokens
    _rec(store, "big", MemoryLayer.SEMANTIC, big + " budgetkeyword")
    query = MemoryQuery(
        task="budgetkeyword", workflow="oc-flow", node="verify", max_records=8, max_tokens=50
    )
    out = retrieve_memory(store, query)
    total = sum(estimate_tokens(r.content) for r in out)
    assert total <= query.max_tokens


def test_retrieval_order_prefers_procedural_over_episodic(store: LocalMemoryStore) -> None:
    _rec(store, "p1", MemoryLayer.PROCEDURAL, "run database migration command")
    _rec(store, "e1", MemoryLayer.EPISODIC, "run database migration episode")
    query = query_for_node("run database migration", "oc-flow", "gather_context")
    query = query.model_copy(update={"max_records": 1})
    out = retrieve_memory(store, query)
    assert len(out) == 1
    assert out[0].layer == MemoryLayer.PROCEDURAL


def test_retrieval_emits_memory_retrieved_event(store: LocalMemoryStore) -> None:
    _rec(store, "s1", MemoryLayer.SEMANTIC, "auth uses AccessResolver centrally")
    emitter = MemoryEventEmitter()
    query = query_for_node("AccessResolver", "oc-flow", "gather_context")
    retrieve_memory(store, query, emitter=emitter)
    assert emitter.of_type(MemoryEvent.RETRIEVED)
