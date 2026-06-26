"""Agent lease primitives for restart-safe coordination.

``AgentCoordinationStore`` persists leases and signals to a SQLite file at
``.opencontext/coordination.db`` using the same WAL-mode connection discipline
as ``SQLiteMemoryBackend``.

Lazy expiry: ``EXPIRED`` status is computed on read when ``expires_at < now()``.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from opencontext_core.compat import UTC, StrEnum

if TYPE_CHECKING:
    from opencontext_core.workflow.signals import AgentSignal, AgentSignalKind


_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_leases (
    lease_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS agent_signals (
    signal_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_leases_run_phase ON agent_leases(run_id, phase, status);
CREATE INDEX IF NOT EXISTS idx_signals_lease ON agent_signals(lease_id);
"""


class AgentLeaseStatus(StrEnum):
    """Status of an agent lease."""

    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"


class AgentLease:
    """A restart-safe lease acquired by an agent for a (run_id, phase) pair."""

    __slots__ = ("acquired_at", "agent_id", "expires_at", "lease_id", "phase", "run_id", "status")

    def __init__(
        self,
        lease_id: str,
        agent_id: str,
        run_id: str,
        phase: str,
        acquired_at: datetime,
        expires_at: datetime,
        status: AgentLeaseStatus = AgentLeaseStatus.ACTIVE,
    ) -> None:
        self.lease_id = lease_id
        self.agent_id = agent_id
        self.run_id = run_id
        self.phase = phase
        self.acquired_at = acquired_at
        self.expires_at = expires_at
        self.status = status


class AgentCoordinationStore:
    """SQLite-backed store for agent leases and signals.

    WAL mode is enabled for concurrent read safety. Lazy expiry transitions
    leases to EXPIRED on read when their ``expires_at`` is in the past.
    """

    def __init__(self, db_path: Path | str = ".opencontext/coordination.db") -> None:
        self._path = str(db_path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
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

    def acquire(
        self,
        agent_id: str,
        run_id: str,
        phase: str,
        duration: timedelta | None = None,
    ) -> AgentLease:
        """Acquire a lease for (agent_id, run_id, phase).

        Raises ``RuntimeError`` if an ACTIVE (non-expired) lease already
        exists for the same (run_id, phase).
        """
        if duration is None:
            duration = timedelta(hours=1)

        now = datetime.now(tz=UTC)
        expires_at = now + duration

        with self._connect() as conn:
            # Check for existing active non-expired lease on same (run_id, phase).
            row = conn.execute(
                """
                SELECT lease_id, expires_at, status
                FROM agent_leases
                WHERE run_id = ? AND phase = ? AND status = 'active'
                LIMIT 1
                """,
                (run_id, phase),
            ).fetchone()

            if row is not None:
                exp = datetime.fromisoformat(row["expires_at"])
                if exp > now:
                    raise RuntimeError(
                        f"Active lease {row['lease_id']!r} already exists for "
                        f"run_id={run_id!r} phase={phase!r}"
                    )
                # Lazy expiry: mark it expired before granting new lease.
                conn.execute(
                    "UPDATE agent_leases SET status = 'expired' WHERE lease_id = ?",
                    (row["lease_id"],),
                )

            lease_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO agent_leases
                (lease_id, agent_id, run_id, phase, acquired_at, expires_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    lease_id,
                    agent_id,
                    run_id,
                    phase,
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )

        return AgentLease(
            lease_id=lease_id,
            agent_id=agent_id,
            run_id=run_id,
            phase=phase,
            acquired_at=now,
            expires_at=expires_at,
            status=AgentLeaseStatus.ACTIVE,
        )

    def release(self, lease_id: str) -> None:
        """Mark a lease as released."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE agent_leases SET status = 'released' WHERE lease_id = ?",
                (lease_id,),
            )

    def get_lease(self, lease_id: str) -> AgentLease | None:
        """Retrieve a lease by ID, applying lazy expiry if needed."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_leases WHERE lease_id = ?",
                (lease_id,),
            ).fetchone()
            if row is None:
                return None

            now = datetime.now(tz=UTC)
            exp = datetime.fromisoformat(row["expires_at"])
            status_str = row["status"]

            if status_str == "active" and exp < now:
                conn.execute(
                    "UPDATE agent_leases SET status = 'expired' WHERE lease_id = ?",
                    (lease_id,),
                )
                status_str = "expired"

            return AgentLease(
                lease_id=row["lease_id"],
                agent_id=row["agent_id"],
                run_id=row["run_id"],
                phase=row["phase"],
                acquired_at=datetime.fromisoformat(row["acquired_at"]),
                expires_at=exp,
                status=AgentLeaseStatus(status_str),
            )

    def signal(
        self,
        lease_id: str,
        kind: AgentSignalKind,
        payload: str | dict[str, Any] | list[Any] | None = None,
    ) -> AgentSignal:
        """Append a signal record for *lease_id*. INSERT-only.

        *payload* may be a ``str``, ``dict``, ``list``, or ``None``.
        Non-string values are serialized to a JSON string before storage.
        The read path returns the raw stored string; callers that need the
        original structure must call ``json.loads()`` themselves.
        """
        from opencontext_core.workflow.signals import AgentSignal

        now = datetime.now(tz=UTC)
        signal_id = str(uuid.uuid4())

        # Serialize structured payloads to JSON string before SQLite bind.
        stored_payload: str | None
        if isinstance(payload, (dict, list)):
            stored_payload = json.dumps(payload, sort_keys=True)
        else:
            stored_payload = payload

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_signals (signal_id, lease_id, kind, created_at, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (signal_id, lease_id, str(kind), now.isoformat(), stored_payload),
            )

        return AgentSignal(
            signal_id=signal_id,
            lease_id=lease_id,
            kind=kind,
            created_at=now,
            payload=stored_payload,
        )

    def release_by_run_phase(self, run_id: str, phase: str) -> None:
        """Release the active lease for (run_id, phase), if one exists.

        Fail-soft: if the row is missing or the query fails, the error is
        silently ignored so callers are never blocked by a stale/absent lease.
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT lease_id FROM agent_leases
                    WHERE run_id = ? AND phase = ? AND status = 'active'
                    LIMIT 1
                    """,
                    (run_id, phase),
                ).fetchone()
                if row is not None:
                    conn.execute(
                        "UPDATE agent_leases SET status = 'released' WHERE lease_id = ?",
                        (row["lease_id"],),
                    )
        except Exception:
            pass

    def get_signals(self, lease_id: str) -> list[AgentSignal]:
        """Retrieve all signals for a lease."""
        from opencontext_core.workflow.signals import AgentSignal, AgentSignalKind

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_signals WHERE lease_id = ? ORDER BY created_at",
                (lease_id,),
            ).fetchall()

        return [
            AgentSignal(
                signal_id=row["signal_id"],
                lease_id=row["lease_id"],
                kind=AgentSignalKind(row["kind"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                payload=row["payload"],
            )
            for row in rows
        ]

    def get_signals_for_run(self, run_id: str) -> list[AgentSignal]:
        """Retrieve signals for all leases in a run, ordered by creation time."""
        from opencontext_core.workflow.signals import AgentSignal, AgentSignalKind

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.* FROM agent_signals s
                JOIN agent_leases l ON l.lease_id = s.lease_id
                WHERE l.run_id = ?
                ORDER BY s.created_at
                """,
                (run_id,),
            ).fetchall()

        return [
            AgentSignal(
                signal_id=row["signal_id"],
                lease_id=row["lease_id"],
                kind=AgentSignalKind(row["kind"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                payload=row["payload"],
            )
            for row in rows
        ]

    def get_active_leases(self, run_id: str | None = None) -> list[AgentLease]:
        """Return active non-expired leases, optionally scoped to *run_id*."""
        now = datetime.now(tz=UTC)
        query = "SELECT * FROM agent_leases WHERE status = 'active'"
        params: tuple[str, ...] = ()
        if run_id is not None:
            query += " AND run_id = ?"
            params = (run_id,)

        leases: list[AgentLease] = []
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            for row in rows:
                exp = datetime.fromisoformat(row["expires_at"])
                if exp < now:
                    conn.execute(
                        "UPDATE agent_leases SET status = 'expired' WHERE lease_id = ?",
                        (row["lease_id"],),
                    )
                    continue
                leases.append(
                    AgentLease(
                        lease_id=row["lease_id"],
                        agent_id=row["agent_id"],
                        run_id=row["run_id"],
                        phase=row["phase"],
                        acquired_at=datetime.fromisoformat(row["acquired_at"]),
                        expires_at=exp,
                        status=AgentLeaseStatus.ACTIVE,
                    )
                )
        return leases
