"""mem_session_end — mark a session row as ended.

REQ-OMT-013 — ``mem_session_end(session_id, *, summary=None) -> SessionRecord``.

Stamps ``ended_at`` on the existing row. ``summary`` is accepted for API
parity with the engram MCP surface; the canonical summary path is
``mem_session_summary`` (REQ-OMT-004) and lives in its own tool.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from opencontext_memory.tools.mem_session_start import SessionRecord


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def mem_session_end(
    store: Any,
    *,
    session_id: str,
    summary: str | None = None,
) -> SessionRecord:
    """Stamp ``ended_at`` on ``session_id`` and return the refreshed row.

    Missing rows raise ``ValueError("session_not_found:<id>")`` so the
    surface can render a 4xx message instead of silently doing nothing.
    The host is expected to call ``mem_session_start`` first; the
    idempotent UPSERT in PR2.c.ii means re-invoking start is harmless.
    """
    del summary  # see mem_session_summary for the canonical summary path.
    now = _utcnow_iso()
    with store._connect() as conn:
        row = conn.execute(
            "SELECT directory, project, started_at, ended_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"session_not_found:{session_id}")
        conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (now, session_id),
        )
    return SessionRecord(
        session_id=session_id,
        directory=row["directory"],
        project=row["project"],
        started_at=row["started_at"],
        ended_at=now,
    )


__all__ = ["mem_session_end"]
