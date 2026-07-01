"""mem_context — recent session history scoped by project / scope.

REQ-OMT-003 — ``mem_context(*, project=None, scope="project", limit=20,
all_projects=False) -> list[RecentObservation]``.

Returns the most recent ``observations`` rows ordered by ``created_at
DESC``. ``all_projects=True`` clears the project filter for a single
host to inspect cross-project context (per REQ-OMPD-003).
"""

from __future__ import annotations

from typing import Any

_CONTEXT_COLUMNS = (
    "id, sync_id, session_id, type, title, content, project, scope, "
    "topic_key, created_at, updated_at, lifecycle_state"
)


def mem_context(
    store: Any,
    *,
    project: str | None = None,
    scope: str = "project",
    limit: int = 20,
    all_projects: bool = False,
) -> list[dict[str, Any]]:
    """Return recent observations, newest first.

    Filters are ANDed; soft-deleted rows are excluded. When
    ``all_projects`` is true the project filter is dropped (the scope
    filter stays). When ``project`` is ``None`` AND ``all_projects`` is
    false, ``project`` is left NULL in the SQL filter, which is exactly
    what ``all_projects=False`` should mean (host-filtered view).
    """
    sql = f"SELECT {_CONTEXT_COLUMNS} FROM observations WHERE deleted_at IS NULL"
    params: list[Any] = []
    if not all_projects:
        sql += " AND project = ?"
        params.append(project)
    if scope is not None:
        sql += " AND scope = ?"
        params.append(scope)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(int(limit))

    with store._connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


__all__ = ["mem_context"]
