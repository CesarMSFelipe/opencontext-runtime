"""Memory migrator + audit (REL-13, book §14).

Memory migrations MUST preserve provenance and MUST NOT silently promote or
delete memories — deprecated records are marked ``stale``/``superseded``, never
erased. This migrator operates on a memory export document (a JSON list of
records): it stamps the schema version and marks any record flagged
``deprecated`` as stale, without dropping a single record. ``audit`` is a
read-only report over the same document.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opencontext_core.migration.harness import MigrationError, MigrationPlan

TARGET_MEMORY_SCHEMA = "opencontext.memory.v1"


def _load(target: Path) -> dict[str, Any]:
    if not target.is_file():
        raise MigrationError(
            f"Memory migration failed: {target} not found.\n"
            f"Suggested fix: export memory first or pass the correct path."
        )
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MigrationError(
            f"Memory migration failed: {target} is not readable JSON ({exc})."
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise MigrationError(
            "Memory migration failed: expected {'schema_version': ..., 'records': [...]}."
        )
    return data


class MemoryMigrator:
    """Migrate a memory export, marking deprecated records stale (never deleting)."""

    domain = "memory"

    def plan(self, target: Path) -> MigrationPlan:
        data = _load(target)
        current = str(data.get("schema_version", "opencontext.memory.v0"))
        records: list[dict[str, Any]] = data["records"]
        to_mark = [
            str(r.get("id", f"#{i}"))
            for i, r in enumerate(records)
            if r.get("deprecated") and not r.get("stale")
        ]
        if current == TARGET_MEMORY_SCHEMA and not to_mark:
            return MigrationPlan(
                domain=self.domain,
                from_version=current,
                to_version=current,
                notes=["memory already current; no deprecated records to mark"],
            )
        bumped = current != TARGET_MEMORY_SCHEMA
        added = [f"schema_version: {TARGET_MEMORY_SCHEMA}"] if bumped else []
        return MigrationPlan(
            domain=self.domain,
            from_version=current,
            to_version=TARGET_MEMORY_SCHEMA,
            added=added,
            marked_stale=to_mark,
            notes=["deprecated records are marked stale/superseded, never deleted (book §14)"],
        )

    def apply(self, target: Path, plan: MigrationPlan) -> None:
        data = _load(target)
        data["schema_version"] = TARGET_MEMORY_SCHEMA
        for record in data["records"]:
            if record.get("deprecated") and not record.get("stale"):
                record["stale"] = True  # mark superseded; provenance preserved
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")


def audit_memory(target: Path | str) -> dict[str, int]:
    """Read-only counts over a memory export (book §14 ``memory audit``)."""
    data = _load(Path(target))
    records: list[dict[str, Any]] = data["records"]
    return {
        "total": len(records),
        "deprecated": sum(1 for r in records if r.get("deprecated")),
        "stale": sum(1 for r in records if r.get("stale")),
    }


__all__ = ["TARGET_MEMORY_SCHEMA", "MemoryMigrator", "audit_memory"]
