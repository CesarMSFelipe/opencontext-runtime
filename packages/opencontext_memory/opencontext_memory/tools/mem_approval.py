"""mem_approve / mem_reject — MEMORY_CONTRACT approval-lifecycle transitions.

``approve`` promotes a ``proposed`` row to ``active`` (the approved default
state, so approved memory flows through recall/search unchanged). ``reject``
marks the row ``rejected`` and soft-deletes it so it is never retrieved again.
Both raise :class:`MemoryNotFound` for unknown or already-deleted ids.
"""

from __future__ import annotations

from typing import Any

from opencontext_memory.store.sqlite import _utcnow_iso
from opencontext_memory.tools.mem_get_observation import MemoryNotFound


def _live_state(store: Any, observation_id: int) -> str:
    with store._connect() as conn:
        row = conn.execute(
            "SELECT lifecycle_state, deleted_at FROM observations WHERE id = ?",
            (int(observation_id),),
        ).fetchone()
    if row is None or row["deleted_at"] is not None:
        raise MemoryNotFound(observation_id)
    return str(row["lifecycle_state"])


def mem_approve(store: Any, *, observation_id: int) -> dict[str, Any]:
    """Promote ``observation_id`` to ``active`` (proposed -> approved)."""
    previous = _live_state(store, observation_id)
    with store._connect() as conn:
        conn.execute(
            "UPDATE observations SET lifecycle_state = 'active', updated_at = ? WHERE id = ?",
            (_utcnow_iso(), int(observation_id)),
        )
    return {
        "id": int(observation_id),
        "previous_state": previous,
        "lifecycle_state": "active",
        "approved": True,
    }


def mem_reject(store: Any, *, observation_id: int) -> dict[str, Any]:
    """Discard ``observation_id``: mark rejected + soft-delete (never retrieved)."""
    previous = _live_state(store, observation_id)
    now = _utcnow_iso()
    with store._connect() as conn:
        conn.execute(
            "UPDATE observations SET lifecycle_state = 'rejected', deleted_at = ?, "
            "updated_at = ? WHERE id = ?",
            (now, now, int(observation_id)),
        )
    return {
        "id": int(observation_id),
        "previous_state": previous,
        "lifecycle_state": "rejected",
        "rejected": True,
    }


__all__ = ["mem_approve", "mem_reject"]
