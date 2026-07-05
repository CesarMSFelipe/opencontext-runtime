"""memory_relations — typed enums and insert helpers for the relations table.

REQ-OMS-004 — relations table accepts 7 verbs x 4 statuses. The :class:`enum.StrEnum`
types mirror the SQL CHECK constraint so an in-process insert cannot accidentally
trip it. ``JudgeBySemantic`` is the helper :func:`mem_compare` (PR2.c) routes through
when persisting a fixed-provenance verdict (``marked_by_actor='engram'``).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RelationVerbs(StrEnum):
    """The 7-verb enum mirroring the SQL CHECK constraint."""

    RELATED = "related"
    COMPATIBLE = "compatible"
    SCOPED = "scoped"
    CONFLICTS_WITH = "conflicts_with"
    SUPERSEDES = "supersedes"
    NOT_CONFLICT = "not_conflict"


class JudgmentStatuses(StrEnum):
    """The 4-state enum mirroring the SQL CHECK constraint."""

    PENDING = "pending"
    JUDGED = "judged"
    ORPHANED = "orphaned"
    IGNORED = "ignored"


# Public alias for callers that pass a raw string into ``insert(verb=...)``.
VerbValue = Literal[
    "related", "compatible", "scoped", "conflicts_with", "supersedes", "not_conflict"
]
StatusValue = Literal["pending", "judged", "orphaned", "ignored"]


class RelationRow(BaseModel):
    """Typed view of a single ``memory_relations`` row.

    Lives here (not in ``models.py``) because it is the direct return shape of
    this module's read helpers; PR2.d will re-export it once the project layer
    lands.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    source_id: int
    target_id: int
    relation: str
    judgment_status: str = "pending"
    marked_by_actor: str
    confidence: float = 1.0
    reasoning: str | None = None
    model: str | None = None
    judgment_id: str | None = None
    created_at: str = Field(description="UTC ISO 8601, suffixed Z.")


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_verb(verb: RelationVerbs | str) -> str:
    """Validate the verb against the enum and return the canonical string.

    Strings are normalised through :class:`RelationVerbs` so a caller passing
    ``"related"`` gets the same row as a caller passing
    ``RelationVerbs.RELATED``. Anything outside the 7 spec'd values raises
    ``ValueError("invalid_relation_verb:<verb>")`` — the exact message the
    spec demands.
    """
    if isinstance(verb, RelationVerbs):
        return verb.value
    if isinstance(verb, str):
        try:
            return RelationVerbs(verb).value
        except ValueError as exc:
            raise ValueError(f"invalid_relation_verb:{verb}") from exc
    raise ValueError(f"invalid_relation_verb:{verb}")


def _coerce_status(status: JudgmentStatuses | str) -> str:
    if isinstance(status, JudgmentStatuses):
        return status.value
    if isinstance(status, str):
        try:
            return JudgmentStatuses(status).value
        except ValueError as exc:
            raise ValueError(f"invalid_judgment_status:{status}") from exc
    raise ValueError(f"invalid_judgment_status:{status}")


def insert(
    connection: sqlite3.Connection,
    source_id: int,
    target_id: int,
    verb: RelationVerbs | VerbValue | str,
    *,
    status: JudgmentStatuses | StatusValue = "pending",
    marked_by_actor: str,
    confidence: float = 1.0,
    reasoning: str | None = None,
    model: str | None = None,
    judgment_id: str | None = None,
) -> int:
    """Insert one ``memory_relations`` row and return its id.

    The caller controls every column except ``id`` and ``created_at``. The
    ``status`` default matches REQ-OCF-001: candidates surface as ``pending``
    so :func:`mem_judge` (PR2.c) can later promote them to ``judged``.
    """
    verb_value = _coerce_verb(verb)
    status_value = _coerce_status(status)
    cur = connection.execute(
        """
        INSERT INTO memory_relations (
            source_id, target_id, relation, judgment_status,
            marked_by_actor, confidence, reasoning, model, judgment_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(source_id),
            int(target_id),
            verb_value,
            status_value,
            marked_by_actor,
            float(confidence),
            reasoning,
            model,
            judgment_id,
            _utcnow_iso(),
        ),
    )
    assert cur.lastrowid is not None, "sqlite returned no lastrowid after insert"
    return int(cur.lastrowid)


def JudgeBySemantic(
    connection: sqlite3.Connection,
    source_id: int,
    target_id: int,
    verb: RelationVerbs | VerbValue | str,
    *,
    confidence: float,
    reasoning: str,
    model: str,
    judgment_id: str | None = None,
) -> int:
    """Insert a semantic verdict with the fixed ``engram`` provenance.

    Mirrors :func:`mem_compare`'s persistence path. ``marked_by_actor`` is
    intentionally NOT a parameter: the spec forbids callers from supplying it.
    """
    return insert(
        connection,
        source_id=source_id,
        target_id=target_id,
        verb=verb,
        status="judged",
        marked_by_actor="engram",
        confidence=confidence,
        reasoning=reasoning,
        model=model,
        judgment_id=judgment_id,
    )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def query_by_source(connection: sqlite3.Connection, source_id: int) -> list[dict[str, Any]]:
    """Return all rows where ``source_id`` matches, ordered by id."""
    rows = connection.execute(
        """
        SELECT id, source_id, target_id, relation, judgment_status, marked_by_actor,
               confidence, reasoning, model, judgment_id, created_at
        FROM memory_relations
        WHERE source_id = ?
        ORDER BY id
        """,
        (int(source_id),),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def query_by_pair(
    connection: sqlite3.Connection,
    *,
    source_id: int,
    target_id: int,
) -> list[dict[str, Any]]:
    """Return rows matching both ``source_id`` and ``target_id``.

    Triangulation helper for ``mem_compare``'s "idempotent re-call updates in
    place" scenario: a re-call finds the existing row instead of inserting a
    duplicate.
    """
    rows = connection.execute(
        """
        SELECT id, source_id, target_id, relation, judgment_status, marked_by_actor,
               confidence, reasoning, model, judgment_id, created_at
        FROM memory_relations
        WHERE source_id = ? AND target_id = ?
        ORDER BY id
        """,
        (int(source_id), int(target_id)),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_judgment(
    connection: sqlite3.Connection,
    *,
    judgment_id: str,
    relation: RelationVerbs | VerbValue | str,
    confidence: float = 1.0,
    reasoning: str | None = None,
) -> int:
    """Promote a relation row to ``judgment_status='judged'``.

    Returns the row id when the update lands, or ``0`` when no row
    matches ``judgment_id``. The :func:`mem_judge` tool (PR2.c.ii)
    surfaces the missing-row case as ``LookupError`` so the host gets a
    clear "judgment_not_found:<id>" message instead of a silent no-op.
    """
    verb_value = _coerce_verb(relation)
    cur = connection.execute(
        """
        UPDATE memory_relations
        SET relation = ?,
            judgment_status = 'judged',
            confidence = ?,
            reasoning = COALESCE(?, reasoning)
        WHERE judgment_id = ?
        """,
        (verb_value, float(confidence), reasoning, judgment_id),
    )
    return int(cur.lastrowid or 0)


def fetch_by_judgment_id(
    connection: sqlite3.Connection,
    judgment_id: str,
) -> dict[str, Any] | None:
    """Return the row for ``judgment_id`` as a dict, or ``None``."""
    row = connection.execute(
        """
        SELECT id, source_id, target_id, relation, judgment_status, marked_by_actor,
               confidence, reasoning, model, judgment_id, created_at
        FROM memory_relations
        WHERE judgment_id = ?
        """,
        (judgment_id,),
    ).fetchone()
    return _row_to_dict(row) if row is not None else None
