"""FTS5 query sanitization.

Before the fix, search_fts passed the raw query into FTS5 MATCH, so any natural
-language task containing punctuation/operators ( ? . ( ) / : - ) raised an
OperationalError that the planner swallowed as 'graph_unavailable' while still
reporting trust='sufficient'. The graph silently contributed nothing.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.indexing.graph_db import GraphDatabase, Node


def _db(tmp_path: Path) -> GraphDatabase:
    db = GraphDatabase(db_path=str(tmp_path / "g.db"))
    db.init_schema()
    # upsert_nodes (not single insert_node) rebuilds the FTS index, matching how
    # the project indexer populates the graph in production.
    db.upsert_nodes(
        [
            Node(
                id=None,
                name="authenticate",
                kind="function",
                file_path="src/auth.py",
                line=1,
                column=0,
                end_line=5,
                language="python",
                container=None,
                docstring="authenticate a user",
                signature="def authenticate()",
                is_exported=True,
            )
        ]
    )
    return db


def test_search_fts_tolerates_punctuation_and_operators(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        # Raw NL query with FTS5-hostile characters must not raise.
        results = db.search_fts("Where is authenticate()? (auth/login) - now")
        assert "authenticate" in [r["name"] for r in results]
    finally:
        db.close()


def test_search_fts_empty_for_punctuation_only_query(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        assert db.search_fts("??? ... /// :::") == []
    finally:
        db.close()
