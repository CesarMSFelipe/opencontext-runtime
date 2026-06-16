"""Stable-id schema migration from a legacy AUTOINCREMENT DB.

An existing `context_graph.db` created with the old AUTOINCREMENT integer `nodes.id`
schema (no `fts_rowid`, no stable text id) must migrate cleanly — re-indexing from
source rebuilds the graph on the new schema without breaking FTS5 / callers / callees.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.graph_db import GraphDatabase
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

_LEGACY_SCHEMA = """
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line INTEGER,
    column INTEGER,
    end_line INTEGER,
    language TEXT NOT NULL,
    container TEXT,
    docstring TEXT,
    signature TEXT,
    is_exported INTEGER DEFAULT 0
);
CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id INTEGER NOT NULL,
    target_node_id INTEGER,
    kind TEXT NOT NULL,
    call_site_file TEXT,
    call_site_line INTEGER
);
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    language TEXT NOT NULL,
    last_modified INTEGER,
    hash TEXT,
    size INTEGER
);
CREATE VIRTUAL TABLE nodes_fts USING fts5(
    name, kind, docstring, signature, content='nodes', content_rowid='id'
);
"""


def _make_legacy_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(_LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO nodes (name, kind, file_path, language) VALUES (?, ?, ?, ?)",
        ("legacy_fn", "function", "old.py", "python"),
    )
    conn.commit()
    conn.close()


def test_init_schema_migrates_legacy_autoincrement_db(tmp_path: Path) -> None:
    db_path = tmp_path / "context_graph.db"
    _make_legacy_db(db_path)

    db = GraphDatabase(db_path=str(db_path))
    db.init_schema()  # must not raise on the legacy schema
    conn = db._connect()
    # After migration the nodes.id column must be TEXT (stable id), not INTEGER.
    cols = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(nodes)").fetchall()}
    assert cols.get("id", "").upper() == "TEXT"
    assert "fts_rowid" in cols
    db.close()


def test_reindex_after_migration_supports_callers_and_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "context_graph.db"
    _make_legacy_db(db_path)

    config = KnowledgeGraphConfig(enabled=True, languages=["python"])
    kg = KnowledgeGraph(config=config, db_path=db_path)
    try:
        (tmp_path / "b.py").write_text("def helper():\n    return 1\n")
        (tmp_path / "a.py").write_text(
            "from b import helper\n\n\ndef caller():\n    return helper()\n"
        )
        kg.index_project(tmp_path)

        # FTS still works on the migrated schema.
        results = kg.search("helper")
        assert any(r["name"] == "helper" for r in results)

        # Callers resolve on the migrated schema.
        conn = kg.db._connect()
        helper_id = conn.execute(
            "SELECT id FROM nodes WHERE name = ? AND file_path = ?", ("helper", "b.py")
        ).fetchone()["id"]
        from opencontext_core.indexing.call_graph import CallGraphAnalyzer

        callers = {c["name"] for c in CallGraphAnalyzer(kg.db).get_callers(helper_id)}
        assert "caller" in callers
    finally:
        kg.close()
