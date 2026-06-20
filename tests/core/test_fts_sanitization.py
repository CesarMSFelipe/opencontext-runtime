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
    db.rebuild_fts()
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


def test_fts_source_scores_best_match_highest(tmp_path: Path) -> None:
    # The FTS source must score the best (first) lexical hit highest. A regression
    # to the old 1/(1-rank) formula inverted this (least-relevant scored highest).
    from opencontext_core.retrieval.planner import FTSRetrievalSource

    db = GraphDatabase(db_path=str(tmp_path / "g.db"))
    db.init_schema()
    db.upsert_nodes(
        [
            Node(
                id=None,
                name=name,
                kind="function",
                file_path=f"src/{name}.py",
                line=1,
                column=0,
                end_line=5,
                language="python",
                container=None,
                docstring="authenticate a user",
                signature=f"def {name}()",
                is_exported=True,
            )
            for name in ("authenticate", "authenticate_user", "reauthenticate")
        ]
    )
    db.rebuild_fts()
    db.close()

    items = FTSRetrievalSource(tmp_path / "g.db", tmp_path).retrieve("authenticate", 10)
    assert len(items) >= 2
    scores = [item.score for item in items]
    assert scores == sorted(scores, reverse=True)  # best-first, not inverted
