"""mem_review — list needs_review observations + mark them as reviewed.

REQ-OMT-009 — ``mem_review(*, action='list'|'mark_reviewed', ...)``.

PR2.c.ii shipped an inline ``DECAY_DAYS`` constant + an inline
``_mark_reviewed`` helper. PR2.d refactors both out:

* ``DECAY_DAYS`` now lives in :mod:`opencontext_memory.lifecycle` (canonical
  per-type decay table for the whole package).
* The mark-reviewed write logic now lives in
  :func:`opencontext_memory.lifecycle.mark_reviewed` (single source of
  truth shared with :mod:`opencontext_memory.diagnostic`).

The wrapper keeps the existing ``action='list'`` shape so the eager tools
that called it keep working unchanged; ``action='mark_reviewed'`` is now
an additive delegate to the lifecycle module.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from opencontext_memory.lifecycle import mark_reviewed

__all__ = ["ObservationSummary", "mem_review"]


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

    ``action='mark_reviewed'`` requires ``observation_id``; delegates to
    :func:`opencontext_memory.lifecycle.mark_reviewed`, which computes
    the new ``review_after`` from the canonical ``DECAY_DAYS`` table and
    returns the refreshed row + audit row.

    Any other verb raises ``ValueError("invalid_review_action:<verb>")``
    so silent contract drift is impossible.
    """
    if action == "list":
        from datetime import UTC, datetime

        now_iso = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
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
        return mark_reviewed(store, observation_id=int(observation_id))

    raise ValueError(f"invalid_review_action:{action}")
