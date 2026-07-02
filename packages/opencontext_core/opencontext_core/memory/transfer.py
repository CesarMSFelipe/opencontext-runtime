"""opencontext_core.memory.transfer — portable memory export/import helpers.

These are the canonical implementations, usable from both the CLI and any
adapter (e.g. claude-code SDD sync_state) without importing from the CLI layer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def memory_export(repo: Any, output: str) -> int:
    """Write all memory items to a shareable JSON file (commit it for the team).

    Returns the number of items exported.
    """
    items = repo.list_items(include_archive=True)
    payload = {
        "version": 1,
        "count": len(items),
        "items": [item.model_dump(mode="json") for item in items],
    }
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Exported {len(items)} memory item(s) to {out}")
    return len(items)


def memory_import(repo: Any, path: str) -> tuple[int, int]:
    """Import memory items from an exported file, skipping IDs already present.

    Returns (imported_count, skipped_count).  Raises SystemExit(1) if the
    file is not found (mirrors the original CLI behaviour).
    """
    from datetime import datetime

    source = Path(path)
    if not source.exists():
        print(f"file not found: {source}", file=sys.stderr)
        raise SystemExit(1)

    payload = json.loads(source.read_text(encoding="utf-8"))
    items = payload.get("items", []) if isinstance(payload, dict) else []
    existing = {item.id for item in repo.list_items(include_archive=True)}
    imported = 0
    skipped = 0
    for entry in items:
        mem_id = entry.get("id")
        if not mem_id or mem_id in existing:
            skipped += 1
            continue
        valid_until = entry.get("valid_until")
        repo.store(
            content=entry.get("content", ""),
            kind=entry.get("kind", "fact"),
            source=entry.get("source", "import"),
            pin=bool(entry.get("pin", False)),
            memory_id=mem_id,
            valid_until=datetime.fromisoformat(valid_until) if valid_until else None,
            metadata=entry.get("metadata") or {},
        )
        imported += 1
    print(f"Imported {imported} item(s), skipped {skipped} (already present or invalid).")
    return imported, skipped


__all__ = ["memory_export", "memory_import"]
