"""mem_compact — consolidate duplicate observations (MEMORY_CONTRACT `compact`).

Equal-content live rows within the same project collapse onto the oldest row
(the id callers already hold via the dedupe-on-save path); later duplicates
are soft-deleted with ``lifecycle_state='compacted'``. Pinned rows are never
compacted (MEM-005/006) and ``proposed`` rows are left for the review queue.
"""

from __future__ import annotations

import hashlib
from typing import Any

from opencontext_memory.store.sqlite import _utcnow_iso


def mem_compact(store: Any) -> dict[str, Any]:
    """Compact duplicates; returns ``{before, after, compacted_ids}``."""
    now = _utcnow_iso()
    with store._connect() as conn:
        rows = conn.execute(
            "SELECT id, content, project, pinned, lifecycle_state FROM observations "
            "WHERE deleted_at IS NULL ORDER BY id"
        ).fetchall()
        before = len(rows)
        seen: set[tuple[Any, str]] = set()
        compacted_ids: list[int] = []
        for row in rows:
            digest = hashlib.sha256(str(row["content"]).encode("utf-8")).hexdigest()
            key = (row["project"], digest)
            if bool(row["pinned"]) or str(row["lifecycle_state"]) == "proposed":
                seen.add(key)
                continue
            if key in seen:
                compacted_ids.append(int(row["id"]))
            else:
                seen.add(key)
        for compacted_id in compacted_ids:
            conn.execute(
                "UPDATE observations SET deleted_at = ?, lifecycle_state = 'compacted', "
                "updated_at = ? WHERE id = ?",
                (now, now, compacted_id),
            )
    return {
        "before": before,
        "after": before - len(compacted_ids),
        "compacted_ids": compacted_ids,
    }


__all__ = ["mem_compact"]
