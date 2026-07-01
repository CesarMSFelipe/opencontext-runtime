"""mem_get_observation — fetch a single observation row by id.

REQ-OMT-005 — ``mem_get_observation(id: int) -> MemoryRecord``. Returns the
full untruncated record; raises :class:`MemoryNotFound` for unknown ids.

The store has no equivalent read helper today, so the tool owns its own
SELECT path. Kept narrow on purpose: this round reads the raw row as a
``dict`` so callers can use the existing ``Observation`` Pydantic model
from PR2.a without coupling the tool to a future ``MemoryRecord`` alias
that lands in PR2.d.
"""

from __future__ import annotations

from typing import Any

_OBSERVATION_COLUMNS = (
    "id, sync_id, session_id, type, title, content, project, scope, "
    "topic_key, revision_count, duplicate_count, created_at, updated_at, "
    "deleted_at, review_after, pinned, lifecycle_state"
)


class MemoryNotFound(LookupError):
    """Raised when ``mem_get_observation`` cannot find ``observation_id``.

    Subclasses ``LookupError`` (not ``KeyError``) because the id is an
    integer row id, not a mapping key. The :attr:`observation_id`
    attribute is preserved for diagnostics.
    """

    def __init__(self, observation_id: int) -> None:
        self.observation_id = int(observation_id)
        super().__init__(f"memory_not_found:{observation_id}")


def mem_get_observation(store: Any, *, observation_id: int) -> dict[str, Any]:
    """Return the observation row for ``observation_id``.

    Soft-deleted rows (where ``deleted_at IS NOT NULL``) are excluded
    from the lookup so callers never receive a "ghost" record. An
    unknown id (or an id of a soft-deleted row) raises
    :class:`MemoryNotFound`.
    """
    with store._connect() as conn:
        row = conn.execute(
            f"SELECT {_OBSERVATION_COLUMNS} FROM observations WHERE id = ? AND deleted_at IS NULL",
            (int(observation_id),),
        ).fetchone()
    if row is None:
        raise MemoryNotFound(observation_id)
    return dict(row)


__all__ = ["MemoryNotFound", "mem_get_observation"]
