"""mem_unpin — reset the ``pinned`` flag on an observation.

REQ-OMT-015 — ``mem_unpin(id) -> dict``. Mirror of :func:`mem_pin`.
"""

from __future__ import annotations

from typing import Any


def mem_unpin(store: Any, *, observation_id: int) -> dict[str, Any]:
    """Set ``pinned = 0`` for ``observation_id`` and return the refreshed row."""
    with store._connect() as conn:
        conn.execute(
            "UPDATE observations SET pinned = 0 WHERE id = ? AND deleted_at IS NULL",
            (int(observation_id),),
        )
    from opencontext_memory.tools.mem_get_observation import mem_get_observation

    return mem_get_observation(store, observation_id=observation_id)


__all__ = ["mem_unpin"]
