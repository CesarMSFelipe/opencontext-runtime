"""mem_delete — soft-delete (default) or hard-delete an observation.

REQ-OMT-019 — ``mem_delete(id, *, hard=False) -> None``.

The default ``soft`` path stamps ``deleted_at`` so the row drops out of
``store.search`` and ``mem_get_observation`` without losing the audit
trail. ``hard=True`` removes the row outright (the spec's "explicit"
branch). Both branches honour the soft-delete-at-once semantics of
``mem_update`` and the rest of the tool surface.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def mem_delete(store: Any, *, observation_id: int, hard: bool = False) -> None:
    """Delete ``observation_id`` (soft by default).

    Hard-delete returns silently when the row does not exist (idempotent
    by design — re-invocations are common from cleanup paths). Soft-
    delete stamps ``deleted_at`` and is a no-op when the row is already
    soft-deleted (so an idempotent call does not stomp the original
    ``deleted_at`` timestamp).
    """
    if hard:
        with store._connect() as conn:
            conn.execute("DELETE FROM observations WHERE id = ?", (int(observation_id),))
        return

    now = _utcnow_iso()
    with store._connect() as conn:
        conn.execute(
            """
            UPDATE observations
            SET deleted_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            (now, int(observation_id)),
        )


__all__ = ["mem_delete"]
