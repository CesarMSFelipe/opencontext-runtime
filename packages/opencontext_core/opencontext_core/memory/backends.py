"""SQLiteMemoryBackend for OpenContext Runtime v2."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord
from opencontext_core.models.evidence import EvidenceRef

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_records (
    id TEXT PRIMARY KEY,
    layer TEXT NOT NULL,
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    source_refs TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    linked_nodes TEXT NOT NULL DEFAULT '[]',
    supersedes TEXT NOT NULL DEFAULT '[]',
    contradicted_by TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
    USING fts5(id UNINDEXED, layer, key, content, tags,
               content='memory_records', content_rowid='rowid');
CREATE INDEX IF NOT EXISTS idx_memory_layer ON memory_records(layer);
CREATE INDEX IF NOT EXISTS idx_memory_key ON memory_records(key);
"""

_FTS_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS memory_fts_insert AFTER INSERT ON memory_records BEGIN
    INSERT INTO memory_fts(rowid, id, layer, key, content, tags)
    VALUES (NEW.rowid, NEW.id, NEW.layer, NEW.key, NEW.content, NEW.tags);
END;
"""

_FTS_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS memory_fts_delete AFTER DELETE ON memory_records BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, id, layer, key, content, tags)
    VALUES ('delete', OLD.rowid, OLD.id, OLD.layer, OLD.key, OLD.content, OLD.tags);
END;
"""


def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
    from datetime import datetime

    source_refs_data = json.loads(row["source_refs"])
    source_refs = [EvidenceRef(**ref) if isinstance(ref, dict) else ref for ref in source_refs_data]
    return MemoryRecord(
        id=row["id"],
        layer=MemoryLayer(row["layer"]),
        key=row["key"],
        content=row["content"],
        confidence=row["confidence"],
        source_refs=source_refs,
        decay_policy=DecayPolicy(enabled=True),
        tags=json.loads(row["tags"]),
        linked_nodes=json.loads(row["linked_nodes"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        supersedes=json.loads(row["supersedes"]),
        contradicted_by=json.loads(row["contradicted_by"]),
    )


class SQLiteMemoryBackend:
    """SQLite + FTS5 memory storage backend."""

    def __init__(self, db_path: Path | str) -> None:
        self._path = str(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.executescript(_FTS_INSERT_TRIGGER)
            conn.executescript(_FTS_DELETE_TRIGGER)

    def store(self, record: MemoryRecord) -> None:
        """Upsert a MemoryRecord."""
        source_refs_json = json.dumps([ref.model_dump() for ref in record.source_refs])
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_records
                (id, layer, key, content, confidence, source_refs, tags,
                 linked_nodes, supersedes, contradicted_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.layer.value,
                    record.key,
                    record.content,
                    record.confidence,
                    source_refs_json,
                    json.dumps(record.tags),
                    json.dumps(record.linked_nodes),
                    json.dumps(record.supersedes),
                    json.dumps(record.contradicted_by),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )

    def search(
        self, query: str, layer: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]:
        """Search using FTS5 MATCH."""
        if not query.strip():
            return []
        # Escape FTS5 special chars
        safe_query = query.replace('"', '""')
        fts_query = f'"{safe_query}"'
        with self._connect() as conn:
            if layer is not None:
                sql = """
                    SELECT r.* FROM memory_records r
                    JOIN memory_fts f ON r.rowid = f.rowid
                    WHERE memory_fts MATCH ? AND r.layer = ?
                    ORDER BY rank
                    LIMIT ?
                """
                rows = conn.execute(sql, (fts_query, layer.value, limit)).fetchall()
            else:
                sql = """
                    SELECT r.* FROM memory_records r
                    JOIN memory_fts f ON r.rowid = f.rowid
                    WHERE memory_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """
                rows = conn.execute(sql, (fts_query, limit)).fetchall()
        return [_row_to_record(row) for row in rows]

    def get_by_key(self, key: str, layer: MemoryLayer | None = None) -> list[MemoryRecord]:
        """Fetch records by exact key."""
        with self._connect() as conn:
            if layer is not None:
                rows = conn.execute(
                    "SELECT * FROM memory_records WHERE key = ? AND layer = ?",
                    (key, layer.value),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memory_records WHERE key = ?",
                    (key,),
                ).fetchall()
        return [_row_to_record(row) for row in rows]

    def delete(self, record_id: str) -> None:
        """Delete a record by ID."""
        with self._connect() as conn:
            conn.execute("DELETE FROM memory_records WHERE id = ?", (record_id,))
