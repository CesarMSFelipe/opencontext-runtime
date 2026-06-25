"""SQLiteMemoryBackend for OpenContext Runtime v2."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryLifecycle,
    MemoryRecord,
)
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
    updated_at TEXT NOT NULL,
    valid_from TEXT,
    invalid_at TEXT,
    superseded_by TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TEXT,
    last_reviewed_at TEXT,
    run_id TEXT,
    provenance TEXT,
    lifecycle TEXT NOT NULL DEFAULT 'candidate'
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


def _fts_match_query(query: str) -> str:
    """Turn an arbitrary natural-language query into a safe FTS5 MATCH expression.

    Extracts bare word tokens, drops 1-char noise, quotes each as a phrase, and
    OR-joins them so any term can match (bm25 ``rank`` then orders by relevance).
    A single rigid phrase would drop recall the moment query terms are not
    perfectly adjacent in the stored content, or the query carries punctuation.
    Returns "" when there are no usable tokens (caller treats that as no match).
    """
    tokens = [t for t in re.findall(r"[A-Za-z0-9_]+", query) if len(t) >= 2]
    return " OR ".join(f'"{t}"' for t in tokens)


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
    source_refs_data = json.loads(row["source_refs"])
    source_refs = [EvidenceRef(**ref) if isinstance(ref, dict) else ref for ref in source_refs_data]
    columns = row.keys()
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
        valid_from=_parse_dt(row["valid_from"]) if "valid_from" in columns else None,
        invalid_at=_parse_dt(row["invalid_at"]) if "invalid_at" in columns else None,
        superseded_by=row["superseded_by"] if "superseded_by" in columns else None,
        topic_key=row["topic_key"] if "topic_key" in columns else None,
        revision_count=row["revision_count"] if "revision_count" in columns else 0,
        run_id=row["run_id"] if "run_id" in columns else None,
        provenance=row["provenance"] if "provenance" in columns else None,
        lifecycle=(
            MemoryLifecycle(row["lifecycle"])
            if "lifecycle" in columns and row["lifecycle"]
            else MemoryLifecycle.CANDIDATE
        ),
    )


class SQLiteMemoryBackend:
    """SQLite + FTS5 memory storage backend."""

    def __init__(self, db_path: Path | str) -> None:
        self._path = str(db_path)
        # Be self-contained: sqlite won't create missing parent directories (it
        # raises "unable to open database file"). The runtime usually pre-creates
        # the storage path, but the public factory must not depend on that.
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # Closes the connection on exit. `with sqlite3.connect()` only commits, it
        # does NOT close — leaking the handle, which on Windows keeps the .db file
        # locked (PermissionError WinError 32) and is a plain resource leak
        # everywhere else.
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.executescript(_FTS_INSERT_TRIGGER)
            conn.executescript(_FTS_DELETE_TRIGGER)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Add columns to databases created before they existed."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(memory_records)")}
        for column in (
            "valid_from",
            "invalid_at",
            "superseded_by",
            "last_accessed_at",
            "last_reviewed_at",
        ):
            if column not in existing:
                conn.execute(f"ALTER TABLE memory_records ADD COLUMN {column} TEXT")
        if "access_count" not in existing:
            conn.execute(
                "ALTER TABLE memory_records ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0"
            )
        if "topic_key" not in existing:
            conn.execute("ALTER TABLE memory_records ADD COLUMN topic_key TEXT")
        if "revision_count" not in existing:
            conn.execute(
                "ALTER TABLE memory_records ADD COLUMN revision_count INTEGER NOT NULL DEFAULT 0"
            )
        for column in ("run_id", "provenance"):
            if column not in existing:
                conn.execute(f"ALTER TABLE memory_records ADD COLUMN {column} TEXT")
        if "lifecycle" not in existing:
            conn.execute(
                "ALTER TABLE memory_records ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'candidate'"
            )

    def store(self, record: MemoryRecord) -> list[str]:
        """Upsert a MemoryRecord. Returns IDs of any records flagged as contradicted."""
        from opencontext_core.memory.contradictions import ContradictionDetector

        source_refs_json = json.dumps([ref.model_dump() for ref in record.source_refs])
        contradicted_ids: list[str] = []

        with self._connect() as conn:
            # Detect conflicts before writing: same key, active records, different content
            existing_rows = conn.execute(
                "SELECT * FROM memory_records WHERE key = ? AND invalid_at IS NULL AND id != ?",
                (record.key, record.id),
            ).fetchall()
            if existing_rows:
                existing = [_row_to_record(r) for r in existing_rows]
                contradicted_ids = ContradictionDetector().detect(record, existing)
                if contradicted_ids:
                    now = datetime.now(tz=UTC).isoformat()
                    for cid in contradicted_ids:
                        # Append new record id to contradicted_by of conflicting record
                        row = conn.execute(
                            "SELECT contradicted_by FROM memory_records WHERE id = ?", (cid,)
                        ).fetchone()
                        if row:
                            by = json.loads(row["contradicted_by"] or "[]")
                            if record.id not in by:
                                by.append(record.id)
                            conn.execute(
                                "UPDATE memory_records SET contradicted_by = ?, updated_at = ? WHERE id = ?",  # noqa: E501
                                (json.dumps(by), now, cid),
                            )

            conn.execute(
                """
                INSERT OR REPLACE INTO memory_records
                (id, layer, key, content, confidence, source_refs, tags,
                 linked_nodes, supersedes, contradicted_by, created_at, updated_at,
                 valid_from, invalid_at, superseded_by, topic_key, revision_count,
                 run_id, provenance, lifecycle)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    record.valid_from.isoformat() if record.valid_from else None,
                    record.invalid_at.isoformat() if record.invalid_at else None,
                    record.superseded_by,
                    record.topic_key,
                    record.revision_count,
                    record.run_id,
                    record.provenance,
                    record.lifecycle.value,
                ),
            )
        return contradicted_ids

    def store_by_topic_key(self, record: MemoryRecord) -> MemoryRecord:
        """Upsert using topic_key as dedup handle, preserving prior versions.

        When a record with the same topic_key already exists, the new content
        does NOT overwrite it in place. The prior row is marked superseded (kept,
        queryable, ``invalid_at`` set) and the new version is inserted, linked
        back via ``supersedes`` with ``revision_count`` carried forward. This
        keeps the dedup path consistent with consolidation — prior state stays
        recoverable instead of being destroyed by an in-place UPDATE. Returns the
        active record (``record`` when a new version was written).
        """
        if not record.topic_key:
            self.store(record)
            return record

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_records WHERE topic_key = ? AND invalid_at IS NULL LIMIT 1",
                (record.topic_key,),
            ).fetchone()

        if row is None:
            self.store(record)
            return record

        existing = _row_to_record(row)
        now = datetime.now(tz=UTC)

        if existing.id == record.id:
            # Same row re-stored under its own id: nothing to supersede, refresh
            # in place (no history is lost — it is the same record).
            with self._connect() as conn:
                conn.execute(
                    """UPDATE memory_records
                       SET content = ?, confidence = ?, tags = ?, updated_at = ?,
                           revision_count = revision_count + 1
                       WHERE id = ?""",
                    (
                        record.content,
                        record.confidence,
                        json.dumps(record.tags),
                        now.isoformat(),
                        existing.id,
                    ),
                )
            existing.content = record.content
            existing.confidence = record.confidence
            existing.tags = record.tags
            existing.updated_at = now
            existing.revision_count += 1
            return existing

        # Distinct id, same topic: supersede the prior version, insert the new
        # one as the active revision. Prior content survives, linked both ways.
        if existing.id not in record.supersedes:
            record.supersedes = [*record.supersedes, existing.id]
        record.revision_count = existing.revision_count + 1
        record.updated_at = now
        self.mark_superseded(existing.id, superseded_by=record.id, invalid_at=now)
        self.store(record)
        return record

    def mark_superseded(self, record_id: str, *, superseded_by: str, invalid_at: datetime) -> None:
        """Mark a record invalid as of a timestamp without deleting it."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE memory_records
                SET invalid_at = ?, superseded_by = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    invalid_at.isoformat(),
                    superseded_by,
                    datetime.now(tz=UTC).isoformat(),
                    record_id,
                ),
            )

    def search(
        self, query: str, layer: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]:
        """Search using FTS5 MATCH."""
        fts_query = _fts_match_query(query)
        if not fts_query:
            return []
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
            # Reinforce by use: a recalled record is one the agent relies on, so
            # bump its access count + recency. decay() spares recently-used rows.
            if rows:
                now = datetime.now(tz=UTC).isoformat()
                conn.executemany(
                    "UPDATE memory_records SET access_count = access_count + 1, "
                    "last_accessed_at = ? WHERE id = ?",
                    [(now, row["id"]) for row in rows],
                )
        return [_row_to_record(row) for row in rows]

    def distinct_keys(self) -> list[str]:
        """Distinct keys with at least one active (not-yet-superseded) record.

        Used by the maintenance sweep to consolidate each key's noisy cluster
        without loading every record. Sorted for deterministic iteration.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT key FROM memory_records WHERE invalid_at IS NULL ORDER BY key"
            ).fetchall()
        return [row["key"] for row in rows]

    def list_records(self, *, limit: int = 200) -> list[MemoryRecord]:
        """All active (not-yet-superseded) records, most-recent first.

        Backs `memory list` so the CLI shows the canonical SQLite store directly.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_records WHERE invalid_at IS NULL "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def get(self, record_id: str) -> MemoryRecord | None:
        """Fetch a single record by id, or None."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_records WHERE id = ?", (record_id,)).fetchone()
        return _row_to_record(row) if row is not None else None

    def mark_reviewed(self, record_id: str) -> bool:
        """Record that a memory was re-confirmed: reset the review clock and bump
        confidence (a review is positive evidence). Returns False if not found.
        """
        now = datetime.now(tz=UTC)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT confidence FROM memory_records WHERE id = ?", (record_id,)
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE memory_records SET last_reviewed_at = ?, confidence = ?, "
                "updated_at = ? WHERE id = ?",
                (now.isoformat(), min(1.0, row["confidence"] + 0.1), now.isoformat(), record_id),
            )
        return True

    def review_due(self, kinds: set[str], older_than_days: int) -> list[MemoryRecord]:
        """Active records of the given kinds not confirmed within the window.

        "Due" = still valid, of a high-stakes kind (a ``kind:<x>`` tag), and last
        reviewed (or, if never, created) more than ``older_than_days`` ago. The age
        cut runs in SQL; the kind filter runs in Python because tags are JSON.
        """
        cutoff = (datetime.now(tz=UTC) - timedelta(days=older_than_days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_records WHERE invalid_at IS NULL "
                "AND COALESCE(last_reviewed_at, created_at) < ? "
                "ORDER BY COALESCE(last_reviewed_at, created_at)",
                (cutoff,),
            ).fetchall()
        wanted = {f"kind:{k}" for k in kinds}
        return [rec for rec in (_row_to_record(r) for r in rows) if wanted & set(rec.tags)]

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
