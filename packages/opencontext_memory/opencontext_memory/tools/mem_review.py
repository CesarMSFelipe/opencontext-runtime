"""mem_review — list needs_review observations + mark them as reviewed.

REQ-OMT-009 — ``mem_review(*, action='list'|'mark_reviewed', ...)``.

The decay policy is intentionally minimal here: PR2.d ships the
canonical ``lifecycle.py`` with the full per-type table and env-override
parser. This module ships the 4-type subset the tests exercise so the
eager + deferred + admin tools can be wired against the same surface
without waiting for the lifecycle module.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict

# ponytail: minimal decay table — PR2.d's lifecycle.py replaces this.
# Each value is the number of days added to "now" when the host marks a
# stale observation as reviewed. Defaults cover the 4 types the eager +
# deferred tools produce; unknown types fall back to 90 days (same as
# the architecture baseline).
DECAY_DAYS: dict[str, int] = {
    "decision": 90,
    "architecture": 180,
    "policy": 365,
    "bugfix": 30,
}

_DEFAULT_DECAY_DAYS = 90


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _utcnow_iso() -> str:
    return _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


class ObservationSummary(BaseModel):
    """Lightweight read view returned by :func:`mem_review` (list action).

    Mirrors the spec's ``ObservationSummary`` shape: just enough metadata
    for the host to decide which rows to refresh, without echoing the
    full content blob.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    type: str
    title: str
    project: str | None
    review_after: str | None
    pinned: bool


_LIST_COLUMNS = "id, type, title, project, review_after, pinned"


def mem_review(
    store: Any,
    *,
    action: str = "list",
    observation_id: int | None = None,
) -> list[ObservationSummary] | dict[str, Any]:
    """List ``needs_review`` rows OR mark one row as reviewed.

    ``action='list'`` returns observations whose ``review_after`` is in
    the past AND not null. Soft-deleted rows are excluded.

    ``action='mark_reviewed'`` requires ``observation_id``; it updates
    ``review_after`` to ``now + DECAY_DAYS[type]`` (or 90 days default)
    and returns the refreshed row as a dict.

    Any other verb raises ``ValueError("invalid_review_action:<verb>")``
    so silent contract drift is impossible.
    """
    if action == "list":
        now_iso = _utcnow_iso()
        with store._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {_LIST_COLUMNS}
                FROM observations
                WHERE deleted_at IS NULL
                  AND review_after IS NOT NULL
                  AND review_after < ?
                ORDER BY review_after ASC
                """,
                (now_iso,),
            ).fetchall()
        return [
            ObservationSummary(
                id=int(r["id"]),
                type=str(r["type"]),
                title=str(r["title"]),
                project=r["project"],
                review_after=r["review_after"],
                pinned=bool(int(r["pinned"])),
            )
            for r in rows
        ]

    if action == "mark_reviewed":
        if observation_id is None:
            raise ValueError("observation_id_required")
        return _mark_reviewed(store, int(observation_id))

    raise ValueError(f"invalid_review_action:{action}")


def _mark_reviewed(store: Any, observation_id: int) -> dict[str, Any]:
    """Apply the per-type decay and write back the new ``review_after``."""
    with store._connect() as conn:
        row = conn.execute(
            "SELECT type FROM observations WHERE id = ? AND deleted_at IS NULL",
            (observation_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"memory_not_found:{observation_id}")
        decay = DECAY_DAYS.get(str(row["type"]), _DEFAULT_DECAY_DAYS)
        new_after = (_utcnow() + timedelta(days=decay)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "UPDATE observations SET review_after = ?, updated_at = ? WHERE id = ?",
            (new_after, _utcnow_iso(), observation_id),
        )
    from opencontext_memory.tools.mem_get_observation import mem_get_observation

    return mem_get_observation(store, observation_id=observation_id)


__all__ = ["DECAY_DAYS", "ObservationSummary", "mem_review"]
