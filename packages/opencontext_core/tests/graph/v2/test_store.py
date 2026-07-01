"""PR-008 KG v2 store tests — T008a.7."""

from __future__ import annotations

import tempfile
from datetime import UTC
from pathlib import Path

import pytest

from opencontext_core.graph.v2.schema import KgEdge, KgEdgeType, KgNode, KgNodeType
from opencontext_core.graph.v2.store import KgStore


@pytest.fixture
def store() -> KgStore:
    with tempfile.TemporaryDirectory() as tmp:
        yield KgStore(Path(tmp) / "test_kg.db")


class TestInsertQuery:
    def test_insert_node_and_query(self, store: KgStore) -> None:
        node = KgNode(id="n:file:test.py", type=KgNodeType.FILE, name="test.py")
        store.insert_node(node)
        results = store.query_nodes_by_type("file")
        assert len(results) == 1
        assert results[0]["id"] == "n:file:test.py"

    def test_insert_edge_and_query(self, store: KgStore) -> None:
        store.insert_node(KgNode(id="n:func:a", type=KgNodeType.FUNCTION, name="a"))
        store.insert_node(KgNode(id="n:func:b", type=KgNodeType.FUNCTION, name="b"))
        edge = KgEdge(id="e:calls:a:b", type=KgEdgeType.CALLS, source="n:func:a", target="n:func:b")
        store.insert_edge(edge)
        results = store.query_edges(source="n:func:a")
        assert len(results) == 1

    def test_search_fts5(self, store: KgStore) -> None:
        store.insert_node(KgNode(id="n:func:auth", type=KgNodeType.FUNCTION, name="authenticate_user"))
        results = store.search("auth")
        assert len(results) >= 1

    def test_superseded_filtered(self, store: KgStore) -> None:
        from datetime import datetime

        from opencontext_core.graph.v2.schema import TemporalMetadata

        node = KgNode(
            id="n:func:old",
            type=KgNodeType.FUNCTION,
            name="old_func",
            temporal=TemporalMetadata(
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                superseded_at=datetime(2026, 6, 1, tzinfo=UTC),
            ),
        )
        store.insert_node(node)
        results = store.query_nodes_by_type("function")
        assert len(results) == 0  # superseded

    def test_overwrite_on_reinsert(self, store: KgStore) -> None:
        n = KgNode(id="n:file:x", type=KgNodeType.FILE, name="x")
        store.insert_node(n)
        store.insert_node(n)
        results = store.query_nodes_by_type("file")
        assert len(results) == 1
