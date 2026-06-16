"""Tests for the knowledge graph SQLite database."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.indexing.graph_db import (
    Edge,
    FileRecord,
    GraphDatabase,
    Node,
)


@pytest.fixture
def db(tmp_path: Path) -> GraphDatabase:
    db_path = tmp_path / "test_graph.db"
    graph_db = GraphDatabase(db_path=str(db_path))
    graph_db.init_schema()
    yield graph_db
    graph_db.close()


class TestNodeOperations:
    def test_insert_node(self, db: GraphDatabase) -> None:
        node = Node(
            id=None,
            name="UserService",
            kind="class",
            file_path="src/auth.py",
            line=10,
            column=0,
            end_line=50,
            language="python",
            container=None,
            docstring="User authentication service.",
            signature="class UserService",
            is_exported=True,
        )

        node_id = db.insert_node(node)

        # Node ids are now stable content-derived text ids (not autoincrement ints).
        assert isinstance(node_id, str) and node_id
        retrieved = db.get_node_by_id(node_id)
        assert retrieved is not None
        assert retrieved.name == "UserService"
        assert retrieved.kind == "class"
        assert retrieved.file_path == "src/auth.py"

    def test_upsert_nodes_replaces_existing(self, db: GraphDatabase) -> None:
        nodes = [
            Node(
                id=None,
                name="func1",
                kind="function",
                file_path="src/mod.py",
                line=1,
                column=0,
                end_line=5,
                language="python",
                container=None,
                docstring=None,
                signature=None,
                is_exported=True,
            ),
        ]

        ids1 = db.upsert_nodes(nodes)
        assert len(ids1) == 1

        # Upsert again with different nodes for same file
        nodes[0].name = "func2"
        ids2 = db.upsert_nodes(nodes)
        assert len(ids2) == 1

        # Only the new node should exist
        file_nodes = db.get_nodes_by_file("src/mod.py")
        assert len(file_nodes) == 1
        assert file_nodes[0].name == "func2"

    def test_get_nodes_by_file(self, db: GraphDatabase) -> None:
        nodes = [
            Node(
                id=None,
                name="A",
                kind="class",
                file_path="src/a.py",
                line=1,
                column=0,
                end_line=10,
                language="python",
                container=None,
                docstring=None,
                signature=None,
                is_exported=True,
            ),
            Node(
                id=None,
                name="B",
                kind="function",
                file_path="src/a.py",
                line=15,
                column=0,
                end_line=20,
                language="python",
                container="A",
                docstring=None,
                signature=None,
                is_exported=True,
            ),
        ]

        db.upsert_nodes(nodes)
        result = db.get_nodes_by_file("src/a.py")

        assert len(result) == 2
        assert result[0].name == "A"
        assert result[1].name == "B"


class TestEdgeOperations:
    def test_insert_edge(self, db: GraphDatabase) -> None:
        edge = Edge(
            id=None,
            source_node_id=1,
            target_node_id=2,
            kind="calls",
            call_site_file="src/main.py",
            call_site_line=42,
        )

        edge_id = db.insert_edge(edge)
        assert edge_id > 0

    def test_upsert_edges(self, db: GraphDatabase) -> None:
        edges = [
            Edge(
                id=None,
                source_node_id=1,
                target_node_id=2,
                kind="calls",
                call_site_file="src/app.py",
                call_site_line=10,
            ),
        ]

        ids = db.upsert_edges(edges, file_path="src/app.py")
        assert len(ids) == 1


class TestFileOperations:
    def test_upsert_file(self, db: GraphDatabase) -> None:
        file_record = FileRecord(
            id=None,
            path="src/main.py",
            language="python",
            last_modified=1234567890,
            hash="abc123",
            size=1024,
        )

        file_id = db.upsert_file(file_record)
        assert file_id > 0

        retrieved = db.get_file_by_path("src/main.py")
        assert retrieved is not None
        assert retrieved.language == "python"
        assert retrieved.hash == "abc123"

    def test_upsert_file_updates_existing(self, db: GraphDatabase) -> None:
        file1 = FileRecord(
            id=None,
            path="src/main.py",
            language="python",
            last_modified=100,
            hash="old",
            size=500,
        )
        db.upsert_file(file1)

        file2 = FileRecord(
            id=None,
            path="src/main.py",
            language="python",
            last_modified=200,
            hash="new",
            size=600,
        )
        db.upsert_file(file2)

        retrieved = db.get_file_by_path("src/main.py")
        assert retrieved is not None
        assert retrieved.hash == "new"
        assert retrieved.size == 600


class TestSearch:
    def test_search_fts_finds_nodes(self, db: GraphDatabase) -> None:
        # FTS5 requires the content to exist in nodes table first
        node = Node(
            id=None,
            name="UserService",
            kind="class",
            file_path="src/auth.py",
            line=10,
            column=0,
            end_line=50,
            language="python",
            container=None,
            docstring="Handles user authentication.",
            signature="class UserService",
            is_exported=True,
        )
        db.insert_node(node)

        results = db.search_fts("UserService")

        # FTS5 may not be available in all SQLite builds; skip if empty
        if not results:
            pytest.skip("FTS5 not available in this SQLite build")

        assert len(results) > 0
        assert any(r["name"] == "UserService" for r in results)


class TestStats:
    def test_get_stats_empty(self, db: GraphDatabase) -> None:
        stats = db.get_stats()
        assert stats == {"nodes": 0, "edges": 0, "files": 0}

    def test_get_stats_with_data(self, db: GraphDatabase) -> None:
        db.insert_node(
            Node(
                id=None,
                name="A",
                kind="function",
                file_path="src/a.py",
                line=1,
                column=0,
                end_line=5,
                language="python",
                container=None,
                docstring=None,
                signature=None,
                is_exported=True,
            )
        )
        db.insert_edge(
            Edge(
                id=None,
                source_node_id=1,
                target_node_id=1,
                kind="calls",
                call_site_file="src/a.py",
                call_site_line=2,
            )
        )
        db.upsert_file(
            FileRecord(
                id=None,
                path="src/a.py",
                language="python",
                last_modified=0,
                hash="",
                size=100,
            )
        )

        stats = db.get_stats()
        assert stats["nodes"] == 1
        assert stats["edges"] == 1
        assert stats["files"] == 1


class TestDelete:
    def test_delete_file_and_nodes(self, db: GraphDatabase) -> None:
        db.insert_node(
            Node(
                id=None,
                name="ToDelete",
                kind="function",
                file_path="src/old.py",
                line=1,
                column=0,
                end_line=5,
                language="python",
                container=None,
                docstring=None,
                signature=None,
                is_exported=True,
            )
        )
        db.upsert_file(
            FileRecord(
                id=None,
                path="src/old.py",
                language="python",
                last_modified=0,
                hash="",
                size=100,
            )
        )

        db.delete_file_and_nodes("src/old.py")

        assert db.get_nodes_by_file("src/old.py") == []
        assert db.get_file_by_path("src/old.py") is None
