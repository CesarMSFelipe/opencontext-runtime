"""mem_session_start — UPSERT the session row.

REQ-OMT-012 (orchestrator override) — the function MUST be idempotent:
a second call with the same ``session_id`` updates the existing row
instead of raising. This closes the loop with the defensive auto-create
``mem_session_summary`` (PR2.c.i) does, so a host can call them in
either order without crashing.

The returned ``SessionRecord`` is the minimal view the host needs to
confirm what landed; full row inspection goes through a follow-up
SELECT (the table has 13 columns — we don't echo them all).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class SessionRecord(BaseModel):
    """Typed echo of the persisted session row.

    Includes only the columns ``mem_session_start`` itself owns. The
    six summary fields owned by ``mem_session_summary`` are intentionally
    NOT echoed here — they default to empty on creation and the host
    shouldn't read stale values.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    directory: str | None
    project: str | None
    started_at: str
    ended_at: str | None


def mem_session_start(
    store: Any,
    *,
    session_id: str,
    directory: str | None = None,
    project: str | None = None,
) -> SessionRecord:
    """Create (or refresh) the ``sessions`` row for ``session_id``.

    The UPSERT keeps ``started_at`` aligned with the most recent call so
    a host that explicitly re-invokes this near the end of a long
    session still gets a sane "when did this session begin" reading.
    """
    now = _utcnow_iso()
    with store._connect() as conn:
        existing = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO sessions (id, directory, project, started_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, directory, project, now),
            )
        else:
            conn.execute(
                """
                UPDATE sessions SET
                    directory = COALESCE(?, directory),
                    project = COALESCE(?, project),
                    started_at = ?
                WHERE id = ?
                """,
                (directory, project, now, session_id),
            )

    return SessionRecord(
        session_id=session_id,
        directory=directory,
        project=project,
        started_at=now,
        ended_at=None,
    )


__all__ = ["SessionRecord", "mem_session_start"]
