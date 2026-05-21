"""SQLite graph database for the code knowledge graph.

Provides schema creation, CRUD operations for nodes, edges, files, and FTS5 search.
Uses SQLite with FTS5 for full-text search across symbol names and docstrings.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Node:
    """A symbol node in the knowledge graph."""

    id: int | None
    name: str
    kind: str
    file_path: str
    line: int
    column: int
    end_line: int
    language: str
    container: str | None
    docstring: str | None
    signature: str | None
    is_exported: bool


@dataclass
class Edge:
    """A relationship edge between two nodes."""

    id: int | None
    source_node_id: int
    target_node_id: int
    kind: str
    call_site_file: str | None
    call_site_line: int | None


@dataclass
class FileRecord:
    """A tracked source file."""

    id: int | None
    path: str
    language: str
    last_modified: int
    hash: str
    size: int


class GraphDatabase:
    """SQLite-backed knowledge graph database.

    Manages nodes (symbols), edges (relationships), files (metadata),
    and FTS5 full-text search index.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS nodes (
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

    CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
    CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path);
    CREATE INDEX IF NOT EXISTS idx_nodes_container ON nodes(container);
    CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);

    CREATE TABLE IF NOT EXISTS edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_node_id INTEGER NOT NULL REFERENCES nodes(id),
        target_node_id INTEGER REFERENCES nodes(id),
        kind TEXT NOT NULL,
        call_site_file TEXT,
        call_site_line INTEGER
    );

    CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_node_id);
    CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_node_id);
    CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind);

    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE NOT NULL,
        language TEXT NOT NULL,
        last_modified INTEGER,
        hash TEXT,
        size INTEGER
    );

    CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);

    CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
        name, kind, docstring, signature,
        content='nodes', content_rowid='id'
    );

    -- Learning system tables
    CREATE TABLE IF NOT EXISTS operation_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation_id TEXT NOT NULL,
        operation_type TEXT NOT NULL,
        query TEXT,
        timestamp TEXT NOT NULL,
        duration_ms REAL DEFAULT 0,
        tokens_used INTEGER DEFAULT 0,
        tokens_budgeted INTEGER DEFAULT 0,
        context_items_selected INTEGER DEFAULT 0,
        context_items_omitted INTEGER DEFAULT 0,
        files_consulted INTEGER DEFAULT 0,
        symbols_consulted INTEGER DEFAULT 0,
        task_type TEXT,
        success INTEGER,
        metadata TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_metrics_operation_type ON operation_metrics(operation_type);
    CREATE INDEX IF NOT EXISTS idx_metrics_task_type ON operation_metrics(task_type);
    CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON operation_metrics(timestamp);

    CREATE TABLE IF NOT EXISTS task_patterns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_type TEXT UNIQUE NOT NULL,
        relevant_symbols TEXT,
        relevant_files TEXT,
        avg_tokens_used INTEGER DEFAULT 0,
        avg_context_items INTEGER DEFAULT 0,
        success_rate REAL DEFAULT 0,
        occurrence_count INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS token_budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation_type TEXT UNIQUE NOT NULL,
        recommended_budget INTEGER DEFAULT 0,
        min_budget INTEGER DEFAULT 0,
        max_budget INTEGER DEFAULT 0,
        avg_actual_usage INTEGER DEFAULT 0,
        efficiency_score REAL DEFAULT 0,
        confidence REAL DEFAULT 0,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS audit_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        query TEXT,
        tokens_used INTEGER DEFAULT 0,
        data_classification TEXT NOT NULL,
        policy_applied TEXT NOT NULL,
        result TEXT,
        checksum TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_records(action);
    CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_records(timestamp);
    """

    def __init__(self, db_path: str | Path = ".storage/opencontext/codegraph.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            # Enable FTS5 if available
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def init_schema(self) -> None:
        """Create tables and indexes."""

        conn = self._connect()
        conn.executescript(self.SCHEMA)
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # Node operations

    def insert_node(self, node: Node) -> int:
        """Insert a node and return its ID."""

        conn = self._connect()
        cursor = conn.execute(
            """
            INSERT INTO nodes (name, kind, file_path, line, column, end_line,
                               language, container, docstring, signature, is_exported)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node.name,
                node.kind,
                node.file_path,
                node.line,
                node.column,
                node.end_line,
                node.language,
                node.container,
                node.docstring,
                node.signature,
                int(node.is_exported),
            ),
        )
        node_id = cursor.lastrowid
        conn.commit()
        return node_id if node_id is not None else 0

    def upsert_nodes(self, nodes: list[Node]) -> list[int]:
        """Bulk insert nodes for a file, deleting existing nodes for that file first."""

        if not nodes:
            return []

        conn = self._connect()
        file_path = nodes[0].file_path

        # Delete existing nodes for this file
        conn.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))

        ids: list[int] = []
        for node in nodes:
            cursor = conn.execute(
                """
                INSERT INTO nodes (name, kind, file_path, line, column, end_line,
                                   language, container, docstring, signature, is_exported)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.name,
                    node.kind,
                    node.file_path,
                    node.line,
                    node.column,
                    node.end_line,
                    node.language,
                    node.container,
                    node.docstring,
                    node.signature,
                    int(node.is_exported),
                ),
            )
            ids.append(cursor.lastrowid if cursor.lastrowid is not None else 0)

        conn.commit()

        # Rebuild FTS5 index to ensure new nodes are searchable
        try:
            conn.execute('INSERT INTO nodes_fts(nodes_fts) VALUES("rebuild")')
            conn.commit()
        except Exception:
            pass

        return ids

    def get_node_by_id(self, node_id: int) -> Node | None:
        """Get a node by ID."""

        conn = self._connect()
        row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()

        if row is None:
            return None

        return Node(
            id=row["id"],
            name=row["name"],
            kind=row["kind"],
            file_path=row["file_path"],
            line=row["line"],
            column=row["column"],
            end_line=row["end_line"],
            language=row["language"],
            container=row["container"],
            docstring=row["docstring"],
            signature=row["signature"],
            is_exported=bool(row["is_exported"]),
        )

    def get_nodes_by_file(self, file_path: str) -> list[Node]:
        """Get all nodes for a file."""

        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM nodes WHERE file_path = ? ORDER BY line", (file_path,)
        ).fetchall()

        return [
            Node(
                id=row["id"],
                name=row["name"],
                kind=row["kind"],
                file_path=row["file_path"],
                line=row["line"],
                column=row["column"],
                end_line=row["end_line"],
                language=row["language"],
                container=row["container"],
                docstring=row["docstring"],
                signature=row["signature"],
                is_exported=bool(row["is_exported"]),
            )
            for row in rows
        ]

    # Edge operations

    def insert_edge(self, edge: Edge) -> int:
        """Insert an edge and return its ID."""

        conn = self._connect()
        cursor = conn.execute(
            """
            INSERT INTO edges (source_node_id, target_node_id, kind,
                               call_site_file, call_site_line)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                edge.source_node_id,
                edge.target_node_id,
                edge.kind,
                edge.call_site_file,
                edge.call_site_line,
            ),
        )
        edge_id = cursor.lastrowid
        conn.commit()
        return edge_id if edge_id is not None else 0

    def upsert_edges(self, edges: list[Edge], file_path: str) -> list[int]:
        """Bulk insert edges for a file, deleting existing edges first."""

        if not edges:
            return []

        conn = self._connect()

        # Delete edges where call_site_file matches
        conn.execute("DELETE FROM edges WHERE call_site_file = ?", (file_path,))

        ids: list[int] = []
        for edge in edges:
            cursor = conn.execute(
                """
                INSERT INTO edges (source_node_id, target_node_id, kind,
                                   call_site_file, call_site_line)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.kind,
                    edge.call_site_file,
                    edge.call_site_line,
                ),
            )
            ids.append(cursor.lastrowid if cursor.lastrowid is not None else 0)

        conn.commit()
        return ids

    # File operations

    def upsert_file(self, file_record: FileRecord) -> int:
        """Insert or update a file record."""

        conn = self._connect()
        cursor = conn.execute(
            """
            INSERT INTO files (path, language, last_modified, hash, size)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                language=excluded.language,
                last_modified=excluded.last_modified,
                hash=excluded.hash,
                size=excluded.size
            """,
            (
                file_record.path,
                file_record.language,
                file_record.last_modified,
                file_record.hash,
                file_record.size,
            ),
        )
        file_id = cursor.lastrowid
        conn.commit()
        return file_id if file_id is not None else 0

    def get_file_by_path(self, path: str) -> FileRecord | None:
        """Get a file record by path."""

        conn = self._connect()
        row = conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()

        if row is None:
            return None

        return FileRecord(
            id=row["id"],
            path=row["path"],
            language=row["language"],
            last_modified=row["last_modified"],
            hash=row["hash"],
            size=row["size"],
        )

    # FTS5 search

    def search_fts(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search nodes using FTS5 full-text search.

        Args:
            query: Search terms.
            limit: Maximum results.

        Returns:
            List of matching node rows with rank.
        """

        conn = self._connect()
        # Escape quotes in query
        safe_query = query.replace('"', '""')

        rows = conn.execute(
            """
            SELECT nodes.*, rank
            FROM nodes_fts
            JOIN nodes ON nodes_fts.rowid = nodes.id
            WHERE nodes_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (safe_query, limit),
        ).fetchall()

        return [
            {
                "id": row["id"],
                "name": row["name"],
                "kind": row["kind"],
                "file_path": row["file_path"],
                "line": row["line"],
                "language": row["language"],
                "container": row["container"],
                "docstring": row["docstring"],
                "signature": row["signature"],
                "rank": row["rank"],
            }
            for row in rows
        ]

    # Statistics

    def get_stats(self) -> dict[str, int]:
        """Return database statistics."""

        conn = self._connect()
        node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

        return {
            "nodes": node_count,
            "edges": edge_count,
            "files": file_count,
        }

    def delete_file_and_nodes(self, file_path: str) -> None:
        """Delete all nodes and edges for a file."""

        conn = self._connect()
        conn.execute("DELETE FROM edges WHERE call_site_file = ?", (file_path,))
        conn.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))
        conn.execute("DELETE FROM files WHERE path = ?", (file_path,))
        conn.commit()

    # ---- Learning system CRUD ----

    def insert_metric(self, metric: dict[str, Any]) -> int:
        """Insert an operation metric."""

        conn = self._connect()
        cursor = conn.execute(
            """
            INSERT INTO operation_metrics
            (operation_id, operation_type, query, timestamp, duration_ms,
             tokens_used, tokens_budgeted, context_items_selected,
             context_items_omitted, files_consulted, symbols_consulted,
             task_type, success, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metric.get("operation_id", ""),
                metric.get("operation_type", ""),
                metric.get("query", ""),
                metric.get("timestamp", ""),
                metric.get("duration_ms", 0),
                metric.get("tokens_used", 0),
                metric.get("tokens_budgeted", 0),
                metric.get("context_items_selected", 0),
                metric.get("context_items_omitted", 0),
                metric.get("files_consulted", 0),
                metric.get("symbols_consulted", 0),
                metric.get("task_type"),
                (
                    1
                    if metric.get("success") is True
                    else (0 if metric.get("success") is False else None)
                ),
                json.dumps(metric.get("metadata", {})),
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0

    def query_metrics(
        self,
        operation_type: str | None = None,
        task_type: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query operation metrics with optional filtering."""

        conn = self._connect()
        sql = "SELECT * FROM operation_metrics WHERE 1=1"
        params: list[Any] = []
        if operation_type:
            sql += " AND operation_type = ?"
            params.append(operation_type)
        if task_type:
            sql += " AND task_type = ?"
            params.append(task_type)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def upsert_task_pattern(self, pattern: dict[str, Any]) -> int:
        """Insert or update a task pattern."""

        conn = self._connect()
        cursor = conn.execute(
            """
            INSERT INTO task_patterns
            (task_type, relevant_symbols, relevant_files, avg_tokens_used,
             avg_context_items, success_rate, occurrence_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_type) DO UPDATE SET
                relevant_symbols=excluded.relevant_symbols,
                relevant_files=excluded.relevant_files,
                avg_tokens_used=excluded.avg_tokens_used,
                avg_context_items=excluded.avg_context_items,
                success_rate=excluded.success_rate,
                occurrence_count=excluded.occurrence_count,
                updated_at=excluded.updated_at
            """,
            (
                pattern["task_type"],
                json.dumps(pattern.get("relevant_symbols", [])),
                json.dumps(pattern.get("relevant_files", [])),
                pattern.get("avg_tokens_used", 0),
                pattern.get("avg_context_items", 0),
                pattern.get("success_rate", 0.0),
                pattern.get("occurrence_count", 0),
                pattern.get("updated_at", ""),
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0

    def get_task_patterns(self) -> list[dict[str, Any]]:
        """Retrieve all learned task patterns."""

        conn = self._connect()
        rows = conn.execute("SELECT * FROM task_patterns").fetchall()
        return [dict(row) for row in rows]

    def upsert_token_budget(self, budget: dict[str, Any]) -> int:
        """Insert or update a token budget profile."""

        conn = self._connect()
        cursor = conn.execute(
            """
            INSERT INTO token_budgets
            (operation_type, recommended_budget, min_budget, max_budget,
             avg_actual_usage, efficiency_score, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(operation_type) DO UPDATE SET
                recommended_budget=excluded.recommended_budget,
                min_budget=excluded.min_budget,
                max_budget=excluded.max_budget,
                avg_actual_usage=excluded.avg_actual_usage,
                efficiency_score=excluded.efficiency_score,
                confidence=excluded.confidence,
                updated_at=excluded.updated_at
            """,
            (
                budget["operation_type"],
                budget.get("recommended_budget", 0),
                budget.get("min_budget", 0),
                budget.get("max_budget", 0),
                budget.get("avg_actual_usage", 0),
                budget.get("efficiency_score", 0.0),
                budget.get("confidence", 0.0),
                budget.get("updated_at", ""),
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0

    def get_token_budgets(self) -> list[dict[str, Any]]:
        """Retrieve all token budget profiles."""

        conn = self._connect()
        rows = conn.execute("SELECT * FROM token_budgets").fetchall()
        return [dict(row) for row in rows]

    def insert_audit_record(self, record: dict[str, Any]) -> int:
        """Insert an audit record."""

        conn = self._connect()
        cursor = conn.execute(
            """
            INSERT INTO audit_records
            (record_id, timestamp, action, actor, query,
             tokens_used, data_classification, policy_applied, result, checksum)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["record_id"],
                record["timestamp"],
                record["action"],
                record["actor"],
                record.get("query", ""),
                record.get("tokens_used", 0),
                record["data_classification"],
                record["policy_applied"],
                record.get("result", ""),
                record["checksum"],
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0

    def query_audit_records(
        self,
        action: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query audit records with optional filtering."""

        conn = self._connect()
        sql = "SELECT * FROM audit_records WHERE 1=1"
        params: list[Any] = []
        if action:
            sql += " AND action = ?"
            params.append(action)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
