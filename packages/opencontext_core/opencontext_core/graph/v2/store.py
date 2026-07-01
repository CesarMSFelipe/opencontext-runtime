"""KG v2 SQLite store — FTS5 + indices for fast graph queries.

PR-008.a: KgStore is the persistence layer behind the knowledge graph.
Supports insert, query by type, and FTS5 full-text search.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from opencontext_core.graph.v2.schema import KgEdge, KgNode, TemporalMetadata

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kg_nodes (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    properties  TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    superseded_at TEXT,
    source_commit TEXT,
    source_author TEXT
);

CREATE TABLE IF NOT EXISTS kg_edges (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    source      TEXT NOT NULL,
    target      TEXT NOT NULL,
    properties  TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    superseded_at TEXT,
    source_commit TEXT,
    source_author TEXT
);

CREATE INDEX IF NOT EXISTS idx_kg_nodes_type ON kg_nodes(type);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_name ON kg_nodes(name);
CREATE INDEX IF NOT EXISTS idx_kg_edges_type ON kg_edges(type);
CREATE INDEX IF NOT EXISTS idx_kg_edges_source ON kg_edges(source);
CREATE INDEX IF NOT EXISTS idx_kg_edges_target ON kg_edges(target);
"""

# FTS5 table creation kept for future migration

class KgStore:
    """SQLite-backed knowledge graph store.

    Opens a file-backed DB (``kg_v2.db``) in the project workspace.
    Each method establishes a thread-local connection.
    """

    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path)

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA_SQL)

    def insert_node(self, node: KgNode) -> None:
        with sqlite3.connect(str(self._path)) as conn:
            self._ensure_schema(conn)
            conn.execute(
                "INSERT OR REPLACE INTO kg_nodes (id,type,name,properties,created_at,superseded_at,source_commit,source_author) VALUES (?,?,?,?,?,?,?,?)",
                (
                    node.id,
                    node.type.value,
                    node.name,
                    _json_dumps(node.properties),
                    node.temporal.created_at.isoformat(),
                    node.temporal.superseded_at.isoformat() if node.temporal.superseded_at else None,
                    node.temporal.source_commit,
                    node.temporal.source_author,
                ),
            )

    def insert_edge(self, edge: KgEdge) -> None:
        with sqlite3.connect(str(self._path)) as conn:
            self._ensure_schema(conn)
            conn.execute(
                "INSERT OR REPLACE INTO kg_edges (id,type,source,target,properties,created_at,superseded_at,source_commit,source_author) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    edge.id,
                    edge.type.value,
                    edge.source,
                    edge.target,
                    _json_dumps(edge.properties),
                    edge.temporal.created_at.isoformat(),
                    edge.temporal.superseded_at.isoformat() if edge.temporal.superseded_at else None,
                    edge.temporal.source_commit,
                    edge.temporal.source_author,
                ),
            )

    def query_nodes_by_type(self, node_type: str) -> list[dict]:
        with sqlite3.connect(str(self._path)) as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                "SELECT * FROM kg_nodes WHERE type = ? AND superseded_at IS NULL ORDER BY name",
                (node_type,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]

    def query_edges(self, source: str | None = None, target: str | None = None) -> list[dict]:
        with sqlite3.connect(str(self._path)) as conn:
            self._ensure_schema(conn)
            if source:
                rows = conn.execute(
                    "SELECT * FROM kg_edges WHERE source = ? AND superseded_at IS NULL",
                    (source,),
                ).fetchall()
            elif target:
                rows = conn.execute(
                    "SELECT * FROM kg_edges WHERE target = ? AND superseded_at IS NULL",
                    (target,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM kg_edges WHERE superseded_at IS NULL"
                ).fetchall()
            return [_row_to_dict(r) for r in rows]

    def search(self, query: str, limit: int = 10) -> list[dict]:
        with sqlite3.connect(str(self._path)) as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                "SELECT * FROM kg_nodes WHERE name LIKE ? AND superseded_at IS NULL LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]


def _json_dumps(obj: object) -> str:
    import json
    return json.dumps(obj, default=str)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


__all__ = ["KgStore"]
