"""mem_update — partial update of an observation row.

REQ-OMT-008 — ``mem_update(id, **fields) -> dict``. Only the fields supplied
are written; unknown field names raise ``ValueError("unknown_field:<name>")``.

The whitelist below intentionally excludes system-managed columns (id,
sync_id, created_at, revision_count, duplicate_count, deleted_at,
lifecycle_state) so the host can never accidentally clobber the
invariants the store relies on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_UPDATABLE_FIELDS = frozenset(
    {
        "title",
        "content",
        "type",
        "project",
        "scope",
        "topic_key",
        "review_after",
        "pinned",
    }
)


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def mem_update(store: Any, *, observation_id: int, **fields: Any) -> dict[str, Any]:
    """Apply a partial update to ``observation_id`` and return the row.

    ``updated_at`` is refreshed on every successful call; ``created_at`` is
    never touched. Soft-deleted rows are also rejected so the host cannot
    accidentally resurrect a deleted observation.
    """
    unknown = set(fields) - _UPDATABLE_FIELDS
    if unknown:
        # Stable error code so the CLI/FastAPI layer can render a 4xx message.
        raise ValueError(f"unknown_field:{sorted(unknown)[0]}")

    if not fields:
        # Nothing to update — still re-fetch and return the current record so
        # the caller's typed ``-> dict`` contract is honoured.
        return _read_row(store, observation_id)

    set_clauses = ", ".join(f"{col} = ?" for col in fields)
    set_clauses += ", updated_at = ?"
    params: list[Any] = [fields[col] for col in fields]
    params.append(_utcnow_iso())
    params.append(int(observation_id))

    with store._connect() as conn:
        conn.execute(
            f"UPDATE observations SET {set_clauses} WHERE id = ? AND deleted_at IS NULL",
            params,
        )
    return _read_row(store, observation_id)


def _read_row(store: Any, observation_id: int) -> dict[str, Any]:
    """Re-fetch the observation row (used by the success path and the
    no-op path of :func:`mem_update`).
    """
    from opencontext_memory.tools.mem_get_observation import mem_get_observation

    return mem_get_observation(store, observation_id=int(observation_id))


__all__ = ["mem_update"]
