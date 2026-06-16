"""Tests for UnifiedGraph — 8 cases."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from opencontext_core.graph.edges import EdgeKind
from opencontext_core.graph.nodes import NodeKind
from opencontext_core.graph.unified import UnifiedGraph, stable_symbol_id
from opencontext_core.memory.agent import NullAgentMemoryStore
from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord


def make_store() -> LocalMemoryStore:
    tmpdir = tempfile.mkdtemp()
    return LocalMemoryStore(Path(tmpdir) / "mem.db")


def make_failure_record(record_id: str = "fail-1") -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=record_id,
        layer=MemoryLayer.FAILURE,
        key=f"failure:{record_id}",
        content="symbol crashed",
        confidence=0.9,
        source_refs=[],
        decay_policy=DecayPolicy(enabled=False),
        tags=[],
        linked_nodes=["ContextPackBuilder"],
        created_at=now,
        updated_at=now,
    )


def test_link_failure_to_symbol_stores_edge() -> None:
    store = NullAgentMemoryStore()
    graph = UnifiedGraph(graph_db=None, memory_store=store)
    record = make_failure_record()
    graph.link_failure_to_symbol(record, "ContextPackBuilder")
    sym_id = stable_symbol_id("ContextPackBuilder")
    assert sym_id in graph._memory_links
    assert any(eid == EdgeKind.BROKE_BEFORE.value for _, eid in graph._memory_links[sym_id])


def test_get_memory_enriched_neighbors_includes_memory_nodes() -> None:
    store = make_store()
    record = make_failure_record()
    store.write(record)
    graph = UnifiedGraph(graph_db=None, memory_store=store)
    graph.link_failure_to_symbol(record, "ContextPackBuilder")
    neighbors = graph.get_memory_enriched_neighbors("ContextPackBuilder", radius=2)
    kinds = {n["node_kind"] for n in neighbors}
    assert NodeKind.MEMORY_BELIEF.value in kinds


def test_two_symbols_same_name_different_files_get_different_ids() -> None:
    from opencontext_core.indexing.knowledge_graph import _stable_symbol_id

    id1 = _stable_symbol_id("proj", "src/a.py", "process", "function")
    id2 = _stable_symbol_id("proj", "src/b.py", "process", "function")
    assert id1 != id2


def test_stable_symbol_id_is_deterministic() -> None:
    id1 = stable_symbol_id("MySymbol")
    id2 = stable_symbol_id("MySymbol")
    assert id1 == id2


def test_add_trace_node_does_not_crash() -> None:
    graph = UnifiedGraph(graph_db=None, memory_store=NullAgentMemoryStore())
    graph.add_trace_node({"run_id": "run-001", "task": "fix bug", "status": "passed"})
    assert len(graph._trace_nodes) == 1


def test_unlinked_symbol_returns_code_only_neighbors() -> None:
    graph = UnifiedGraph(graph_db=None, memory_store=NullAgentMemoryStore())
    neighbors = graph.get_memory_enriched_neighbors("UnlinkedSymbol", radius=2)
    # No graph_db and no links → empty
    assert isinstance(neighbors, list)


def test_null_agent_memory_store_works() -> None:
    graph = UnifiedGraph(graph_db=None, memory_store=NullAgentMemoryStore())
    record = make_failure_record()
    graph.link_failure_to_symbol(record, "SomeSymbol")
    neighbors = graph.get_memory_enriched_neighbors("SomeSymbol", radius=1)
    assert isinstance(neighbors, list)


def test_edge_kind_values_used_correctly() -> None:
    graph = UnifiedGraph(graph_db=None, memory_store=NullAgentMemoryStore())
    graph.link_memory_to_symbol("mem-1", "sym-1", EdgeKind.APPLIES_TO)
    assert any(e["edge_kind"] == EdgeKind.APPLIES_TO.value for e in graph._edges)
