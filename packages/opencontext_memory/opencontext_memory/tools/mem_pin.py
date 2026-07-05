"""mem_pin — flip the ``pinned`` flag on an observation.

REQ-OMT-014 — ``mem_pin(id) -> dict``. Per-session, not synced: the
flag lives in the ``observations`` table and follows the rest of the
soft-delete semantics.
"""

from __future__ import annotations

from typing import Any


def mem_pin(store: Any, *, observation_id: int) -> dict[str, Any]:
    """Set ``pinned = 1`` for ``observation_id`` and return the refreshed row."""
    with store._connect() as conn:
        conn.execute(
            "UPDATE observations SET pinned = 1 WHERE id = ? AND deleted_at IS NULL",
            (int(observation_id),),
        )
    from opencontext_memory.tools.mem_get_observation import mem_get_observation

    return mem_get_observation(store, observation_id=observation_id)


__all__ = ["mem_pin"]
