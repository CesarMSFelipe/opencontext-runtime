"""mem_session_summary — persist a structured six-field session summary.

REQ-OMT-004 — ``mem_session_summary(session_id, *, goal, instructions="",
discoveries, accomplished, next_steps, relevant_files) -> None``.

The six structured fields land in the ``sessions`` table. List fields are
JSON-encoded so the cell stays a single TEXT value (the table column is
plain TEXT — there is no separate ``session_summaries`` table).

The function is idempotent: re-invoking with the same ``session_id``
overwrites the six summary columns (``goal`` .. ``relevant_files``) and
bumps ``summary_created_at``. ``started_at`` and ``ended_at`` are owned
by ``mem_session_start`` / ``mem_session_end`` and are NEVER touched here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class SessionSummaryError(ValueError):
    """Raised when ``mem_session_summary`` rejects its input."""


class SessionSummaryRecord(BaseModel):
    """Typed echo of the six persisted fields.

    Returned so the caller can confirm what landed without a follow-up
    SELECT; matches the dict-only shape the spec describes for the rest
    of the tool surface.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    goal: str
    instructions: str
    discoveries: list[str]
    accomplished: list[str]
    next_steps: list[str]
    relevant_files: list[str]
    summary_created_at: str = Field(description="UTC ISO 8601, suffixed Z.")


def mem_session_summary(
    store: Any,
    *,
    session_id: str,
    goal: str,
    instructions: str = "",
    discoveries: list[str],
    accomplished: list[str],
    next_steps: list[str],
    relevant_files: list[str],
) -> SessionSummaryRecord:
    """Persist a structured summary for ``session_id``.

    Empty ``goal`` raises :class:`SessionSummaryError` (which subclasses
    ``ValueError``) carrying the exact message ``"goal_required"`` so the
    CLI / FastAPI layer can surface it verbatim.

    The session row MUST exist before summary — ``mem_session_start``
    creates it; if a caller invokes this tool without first starting the
    session, the row is auto-created here so the summary path is robust
    to ordering (the row's ``started_at`` defaults to ``summary_created_at``
    in that case to satisfy the NOT NULL constraint).
    """
    if not goal:
        raise SessionSummaryError("goal_required")

    now = _utcnow_iso()
    discoveries_json = json.dumps(list(discoveries))
    accomplished_json = json.dumps(list(accomplished))
    next_steps_json = json.dumps(list(next_steps))
    relevant_files_json = json.dumps(list(relevant_files))

    with store._connect() as conn:
        existing = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, directory, project, started_at, ended_at,
                    goal, instructions, discoveries, accomplished,
                    next_steps, relevant_files, summary_created_at
                ) VALUES (?, NULL, NULL, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    now,
                    goal,
                    instructions,
                    discoveries_json,
                    accomplished_json,
                    next_steps_json,
                    relevant_files_json,
                    now,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE sessions SET
                    goal = ?,
                    instructions = ?,
                    discoveries = ?,
                    accomplished = ?,
                    next_steps = ?,
                    relevant_files = ?,
                    summary_created_at = ?
                WHERE id = ?
                """,
                (
                    goal,
                    instructions,
                    discoveries_json,
                    accomplished_json,
                    next_steps_json,
                    relevant_files_json,
                    now,
                    session_id,
                ),
            )

    return SessionSummaryRecord(
        session_id=session_id,
        goal=goal,
        instructions=instructions,
        discoveries=list(discoveries),
        accomplished=list(accomplished),
        next_steps=list(next_steps),
        relevant_files=list(relevant_files),
        summary_created_at=now,
    )


__all__ = ["SessionSummaryError", "SessionSummaryRecord", "mem_session_summary"]
