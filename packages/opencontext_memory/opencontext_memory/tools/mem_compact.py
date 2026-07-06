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
    """Compact duplicates; returns ``{before, after, compacted_ids, clusters}``.

    ``clusters`` (additive) describes each compacted duplicate cluster as
    ``{keeper_id, title, compacted_ids}`` so callers (MEM-006: the CLI compact
    verb) can generate a summary record of what was consolidated.
    """
    now = _utcnow_iso()
    with store._connect() as conn:
        rows = conn.execute(
            "SELECT id, title, content, project, pinned, lifecycle_state FROM observations "
            "WHERE deleted_at IS NULL ORDER BY id"
        ).fetchall()
        before = len(rows)
        keepers: dict[tuple[Any, str], dict[str, Any]] = {}
        compacted_ids: list[int] = []
        for row in rows:
            digest = hashlib.sha256(str(row["content"]).encode("utf-8")).hexdigest()
            key = (row["project"], digest)
            entry = {"keeper_id": int(row["id"]), "title": str(row["title"]), "compacted_ids": []}
            if bool(row["pinned"]) or str(row["lifecycle_state"]) == "proposed":
                keepers.setdefault(key, entry)
                continue
            if key in keepers:
                compacted_ids.append(int(row["id"]))
                keepers[key]["compacted_ids"].append(int(row["id"]))
            else:
                keepers[key] = entry
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
        "clusters": [c for c in keepers.values() if c["compacted_ids"]],
    }


__all__ = ["mem_compact"]
