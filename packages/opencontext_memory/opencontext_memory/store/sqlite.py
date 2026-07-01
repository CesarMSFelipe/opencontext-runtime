"""MemoryStore — SQLite + FTS5 observation store.

Single source of truth for ``store/schema.sql``; the class loads it on first
open and never edits it directly. Migrations land in ``store/migrations.py``
(PR2.b) and stay additive unless the migrate flag is explicit.

Concurrency:

* Per-connection ``threading.Lock`` serialises writes within one process.
* Cross-process writes go through :class:`opencontext_memory.WriteQueue`,
  which uses ``fcntl.flock`` on POSIX and a ``msvcrt``-compatible lockfile on
  Windows.
* Upserts are driven by a partial UNIQUE index on
  ``(topic_key, project, scope) WHERE deleted_at IS NULL AND topic_key IS NOT NULL``
  so the same ``INSERT ... ON CONFLICT`` statement handles fresh inserts and
  in-place revisions without an explicit SELECT-then-UPDATE round-trip.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from opencontext_memory.store.write_queue import WriteQueue

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class Observation(BaseModel):
    """A single observation row to write to the store.

    Mirrors the columns declared in ``store/schema.sql``. Fields with defaults
    keep the in-memory construction ergonomic; the store fills any unset
    server-side fields (``sync_id``, ``revision_count``, ``created_at``, …) on
    insert.
    """

    model_config = ConfigDict(extra="forbid")

    sync_id: str | None = Field(
        default=None, description="External sync id (auto-assigned if omitted)."
    )
    session_id: str = Field(description="Originating session id.")
    type: str = Field(default="mem_save", description="Tool / channel that produced the row.")
    title: str = Field(description="Short human-readable title.")
    content: str = Field(description="Observation body.")
    project: str | None = Field(default=None, description="Owning project handle.")
    scope: str = Field(default="project", description="Scope ('project', 'user', ...).")
    topic_key: str | None = Field(default=None, description="Upsert handle.")
    review_after: str | None = Field(default=None, description="ISO timestamp for next review.")
    pinned: bool = Field(default=False, description="Pin against lifecycle decay.")


class ObservationWriteResult(BaseModel):
    """Return value of :meth:`MemoryStore.write`."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(description="Row id (existing on upsert, new on insert).")
    upserted: bool = Field(description="True when an existing topic_key row was updated in place.")


def _utcnow_iso() -> str:
    """UTC ISO 8601 with seconds precision, suffixed ``Z``."""
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class MemoryStore:
    """SQLite + FTS5 observation store with topic-key upsert.

    Construct via :meth:`open` so the schema is applied idempotently. The
    store keeps a single shared connection guarded by a per-instance lock;
    writes route through a :class:`WriteQueue` when the caller passes one.
    """

    def __init__(
        self, connection: sqlite3.Connection, *, write_queue: WriteQueue | None = None
    ) -> None:
        self._conn = connection
        self._conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._write_queue = write_queue

    # -- lifecycle -----------------------------------------------------------

    @classmethod
    def open(cls, db_path: Path, *, write_queue: WriteQueue | None = None) -> MemoryStore:
        """Open (or create) a SQLite database and apply the canonical schema.

        ``db_path`` is created if it does not exist; the parent directory must
        already be present (matches the ``.opencontext/`` layout the runtime
        provisions on ``opencontext init``).
        """
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        cls._apply_schema(conn)
        return cls(conn, write_queue=write_queue)

    @classmethod
    def _apply_schema(cls, conn: sqlite3.Connection) -> None:
        """Apply the canonical DDL if the ``observations`` table is missing.

        Uses ``CREATE TABLE IF NOT EXISTS``-style idempotent DDL extracted from
        ``schema.sql``. We split on ``;`` because Python's sqlite3 driver
        cannot run a multi-statement script in ``isolation_level=None`` mode
        without an explicit ``executescript`` — which silently disables
        ``PRAGMA`` statements above. So we replay the DDL statements we need
        directly here, in order.
        """
        conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        # Partial unique index driving topic_key upsert. Lives next to schema
        # but declared here because ON CONFLICT requires the matching predicate.
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS observations_unique_topic
                ON observations(topic_key, project, scope)
                WHERE deleted_at IS NULL AND topic_key IS NOT NULL
            """
        )

    def close(self) -> None:
        """Close the underlying connection. Safe to call multiple times."""
        with self._write_lock:
            self._conn.close()

    def _connect(self) -> _ConnectionCtx:
        """Borrow the shared connection for read-only inspection (tests)."""

        return _ConnectionCtx(self._conn, self._write_lock)

    # -- write ---------------------------------------------------------------

    def write(self, observation: Observation) -> int:
        """Insert or upsert an observation, returning the row id.

        When ``topic_key`` (with matching ``project`` + ``scope``) matches a
        live row, the existing row is updated in place, ``revision_count``
        increments, and the original id is returned. Otherwise a fresh row is
        inserted and its FTS mirror row is added.
        """
        if self._write_queue is not None:
            with self._write_queue:
                return self._write_locked(observation)
        with self._write_lock:
            return self._write_locked(observation)

    def _write_locked(self, observation: Observation) -> int:
        now = _utcnow_iso()
        sync_id = observation.sync_id or f"sync-{uuid4().hex}"
        params = (
            sync_id,
            observation.session_id,
            observation.type,
            observation.title,
            observation.content,
            observation.project,
            observation.scope,
            observation.topic_key,
            now,
            now,
            observation.review_after,
            int(observation.pinned),
        )
        cur = self._conn.execute(
            """
            INSERT INTO observations (
                sync_id, session_id, type, title, content,
                project, scope, topic_key,
                created_at, updated_at, review_after, pinned
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic_key, project, scope)
                WHERE deleted_at IS NULL AND topic_key IS NOT NULL
            DO UPDATE SET
                sync_id = excluded.sync_id,
                session_id = excluded.session_id,
                type = excluded.type,
                title = excluded.title,
                content = excluded.content,
                review_after = excluded.review_after,
                pinned = excluded.pinned,
                updated_at = excluded.updated_at,
                revision_count = revision_count + 1
            """,
            params,
        )
        # ON CONFLICT may either INSERT (returning lastrowid) or UPDATE
        # (returning 0). For UPDATE we recover the existing id with a SELECT.
        new_id = cur.lastrowid or 0
        if new_id == 0:
            existing = self._conn.execute(
                """
                SELECT id FROM observations
                WHERE topic_key = ? AND project = ? AND scope = ?
                  AND deleted_at IS NULL
                """,
                (observation.topic_key, observation.project, observation.scope),
            ).fetchone()
            assert existing is not None, "topic_key upsert lost the target row"
            new_id = int(existing["id"])
        else:
            # Fresh insert: mirror to FTS5.
            self._conn.execute(
                "INSERT INTO observations_fts(rowid, title, content) VALUES (?, ?, ?)",
                (new_id, observation.title, observation.content),
            )
        return new_id

    # -- search --------------------------------------------------------------

    def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Return up to ``limit`` observations ranked by FTS5 BM25.

        Soft-deleted rows (``deleted_at IS NOT NULL``) are excluded. BM25
        ranks lower-is-better in SQLite FTS5, so we ``ORDER BY rank`` (no
        qualifier) — the most relevant row lands at index 0.
        """
        rows = self._conn.execute(
            """
            SELECT o.id, o.title, o.content, o.project, o.scope,
                   o.topic_key, o.type, o.created_at, o.updated_at,
                   bm25(observations_fts) AS rank
            FROM observations_fts
            JOIN observations o ON o.id = observations_fts.rowid
            WHERE observations_fts MATCH ?
              AND o.deleted_at IS NULL
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [dict(row) for row in rows]


class _ConnectionCtx:
    """Tiny context manager that borrows the shared connection under the
    per-instance write lock. Reads only; writes should go through :meth:`write`.
    """

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock) -> None:
        self._conn = conn
        self._lock = lock

    def __enter__(self) -> sqlite3.Connection:
        self._lock.acquire()
        return self._conn

    def __exit__(self, *_: object) -> None:
        self._lock.release()
