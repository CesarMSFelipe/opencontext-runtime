"""SQLite graph database for the code knowledge graph.

Provides schema creation, CRUD operations for nodes, edges, files, and FTS5 search.
Uses SQLite with FTS5 for full-text search across symbol names and docstrings.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _sanitize_fts_query(query: str) -> str:
    """Turn an arbitrary natural-language query into a safe FTS5 MATCH expression.

    Extracts bare word tokens (letters/digits/underscore), drops 1-char noise,
    quotes each as a phrase, and OR-joins them so any term can match. Returns ""
    when the query has no usable tokens (the caller treats that as "no results").
    """
    tokens = [t for t in re.findall(r"[A-Za-z0-9_]+", query) if len(t) >= 2]
    return " OR ".join(f'"{t}"' for t in tokens)


def _fts_rowid(stable_id: str) -> int:
    """Derive a deterministic int64 FTS5 rowid from a stable text id.

    FTS5 external-content tables require an integer ``content_rowid``. We take the
    first 15 hex chars (60 bits, well inside signed int64) of the stable id so the
    FTS rowid is itself content-derived and survives delete+reinsert.
    """
    try:
        return int(stable_id[:15], 16)
    except (ValueError, TypeError):
        # Legacy integer ids (e.g. test fixtures inserting raw ints) pass through.
        return int(stable_id)


@dataclass
class Node:
    """A symbol node in the knowledge graph."""

    id: str | None
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
    content_snippet: str | None = None


@dataclass
class Edge:
    """A relationship edge between two nodes."""

    id: int | None
    source_node_id: str
    target_node_id: str
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
        id TEXT PRIMARY KEY,
        fts_rowid INTEGER UNIQUE,
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
        is_exported INTEGER DEFAULT 0,
        content_snippet TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
    CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path);
    CREATE INDEX IF NOT EXISTS idx_nodes_container ON nodes(container);
    CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);

    CREATE TABLE IF NOT EXISTS edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_node_id TEXT NOT NULL,
        target_node_id TEXT,
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
        name, kind, docstring, signature, file_path, content_snippet,
        content='nodes', content_rowid='fts_rowid'
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

    def __init__(self, db_path: str | Path = ".storage/opencontext/context_graph.db") -> None:
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            legacy_path = self.db_path.with_name("code" + "graph.db")
            if self.db_path.name == "context_graph.db" and legacy_path.exists():
                self.db_path = legacy_path
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
        """Create tables and indexes, migrating legacy schemas first."""

        conn = self._connect()
        self._migrate_legacy_schema(conn)
        self._migrate_fts_schema(conn)
        conn.executescript(self.SCHEMA)
        conn.commit()

    def _migrate_fts_schema(self, conn: sqlite3.Connection) -> None:
        """Upgrade the FTS5 index if it is missing file_path / content_snippet columns.

        SQLite FTS5 virtual tables cannot be altered in place — we drop and let
        init_schema recreate it, then rebuild from the nodes content table.
        The nodes table also gets content_snippet added via ALTER TABLE if absent;
        ALTER TABLE ADD COLUMN is safe here because the column is nullable TEXT.
        """
        # Add content_snippet column to nodes if missing (safe ALTER TABLE ADD COLUMN).
        existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(nodes)")}
        if "content_snippet" not in existing_cols and existing_cols:
            conn.execute("ALTER TABLE nodes ADD COLUMN content_snippet TEXT")
            conn.commit()

        # Check FTS5 schema via sqlite_master; drop if file_path not indexed.
        fts_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='nodes_fts'"
        ).fetchone()
        if fts_row and "file_path" not in (fts_row[0] or ""):
            conn.execute("DROP TABLE IF EXISTS nodes_fts")
            conn.commit()

    def _migrate_legacy_schema(self, conn: sqlite3.Connection) -> None:
        """Drop the legacy AUTOINCREMENT graph tables so the new stable-id schema applies.

        Stable node identity is content-derived and file-scoped; a legacy DB stored
        AUTOINCREMENT integer ids with no recoverable stable identity, so we cannot
        losslessly convert in place. We drop only the graph tables (nodes/edges/files
        and the FTS index) — the learning/audit tables are untouched — and the caller
        reindexes from source onto the new schema. Idempotent: a fresh or already-new
        DB is left alone.
        """
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nodes'"
        ).fetchone()
        if row is None:
            return  # fresh DB; nothing to migrate

        cols = {
            r["name"]: (r["type"] or "").upper() for r in conn.execute("PRAGMA table_info(nodes)")
        }
        # New schema => id is TEXT and fts_rowid exists. Migrate only if either is missing.
        if cols.get("id") == "TEXT" and "fts_rowid" in cols:
            return

        for stmt in (
            "DROP TABLE IF EXISTS nodes_fts",
            "DROP TABLE IF EXISTS edges",
            "DROP TABLE IF EXISTS nodes",
            "DROP TABLE IF EXISTS files",
        ):
            conn.execute(stmt)
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        # Close the cached connection when the object is collected, so a caller
        # that forgets to call close() doesn't leave the .db locked on Windows
        # (PermissionError WinError 32). Guarded for interpreter shutdown.
        try:
            self.close()
        except Exception:
            pass

    # Node operations

    def insert_node(self, node: Node) -> str:
        """Insert a node and return its stable ID.

        If ``node.id`` is set it is used as the stable id; otherwise a deterministic
        id is derived from the node's file path / qualified name / kind so the same
        symbol always maps to the same id (see ``_stable_symbol_id``).
        """

        from opencontext_core.indexing.knowledge_graph import _stable_symbol_id

        conn = self._connect()
        qualified = f"{node.container}.{node.name}" if node.container else node.name
        node_id = node.id or _stable_symbol_id("", node.file_path, qualified, node.kind)
        conn.execute(
            """
            INSERT OR REPLACE INTO nodes (id, fts_rowid, name, kind, file_path, line, column,
                               end_line, language, container, docstring, signature, is_exported,
                               content_snippet)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                _fts_rowid(node_id),
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
                node.content_snippet,
            ),
        )
        conn.commit()
        return node_id

    def upsert_nodes(self, nodes: list[Node], project_id: str = "") -> list[str]:
        """Bulk upsert nodes for a file using stable, content-derived ids.

        Stable identity (``_stable_symbol_id``) means an unchanged symbol keeps the
        same id across re-index, so inbound cross-file edges that reference it are NOT
        orphaned. Rather than DELETE-all-then-INSERT (which minted fresh ids and
        orphaned inbound edges), we INSERT OR REPLACE the current symbols and prune
        only nodes of this file that no longer exist (removing their own edges).
        """

        if not nodes:
            return []

        from opencontext_core.indexing.knowledge_graph import _stable_symbol_id

        conn = self._connect()
        file_path = nodes[0].file_path

        ids: list[str] = []
        for node in nodes:
            qualified = f"{node.container}.{node.name}" if node.container else node.name
            node_id = node.id or _stable_symbol_id(project_id, node.file_path, qualified, node.kind)
            node.id = node_id
            ids.append(node_id)
            conn.execute(
                """
                INSERT OR REPLACE INTO nodes (id, fts_rowid, name, kind, file_path, line, column,
                                   end_line, language, container, docstring, signature, is_exported,
                                   content_snippet)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    _fts_rowid(node_id),
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
                    node.content_snippet,
                ),
            )

        # Prune nodes of this file that are no longer present (symbol removed/renamed).
        # Only their OWN edges go with them; inbound edges to surviving ids stay intact.
        # Write-guard: skip deletion for nodes still referenced by other files — a
        # full re-index or the referencing file's next re-index will clean up orphans.
        keep = set(ids)
        stale = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM nodes WHERE file_path = ?", (file_path,)
            ).fetchall()
            if row["id"] not in keep
        ]
        for stale_id in stale:
            inbound = conn.execute(
                "SELECT COUNT(*) FROM edges WHERE target_node_id = ? AND call_site_file != ?",
                (stale_id, file_path),
            ).fetchone()[0]
            if inbound > 0:
                continue
            conn.execute(
                "DELETE FROM edges WHERE source_node_id = ? OR target_node_id = ?",
                (stale_id, stale_id),
            )
            conn.execute("DELETE FROM nodes WHERE id = ?", (stale_id,))

        conn.commit()

        # Rebuild FTS5 index to ensure new nodes are searchable
        try:
            conn.execute('INSERT INTO nodes_fts(nodes_fts) VALUES("rebuild")')
            conn.commit()
        except Exception:
            pass

        return ids

    def get_node_by_id(self, node_id: int | str) -> Node | None:
        """Get a node by ID (stable text id; ints are accepted and coerced by SQLite)."""

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

    def all_files(self) -> list[FileRecord]:
        """Every indexed file record (used to detect staleness vs disk)."""
        conn = self._connect()
        rows = conn.execute("SELECT * FROM files ORDER BY path").fetchall()
        return [
            FileRecord(
                id=row["id"],
                path=row["path"],
                language=row["language"],
                last_modified=row["last_modified"],
                hash=row["hash"],
                size=row["size"],
            )
            for row in rows
        ]

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
        # Sanitize for FTS5: tokenize into bare words and quote each as a phrase,
        # OR-joined. Raw natural-language queries contain FTS5 operators/punctuation
        # ( ? . ( ) / : - ) that otherwise raise a syntax error.
        safe_query = _sanitize_fts_query(query)
        if not safe_query:
            return []

        rows = conn.execute(
            """
            SELECT nodes.*, rank
            FROM nodes_fts
            JOIN nodes ON nodes_fts.rowid = nodes.fts_rowid
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
