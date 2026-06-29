"""Knowledge-Graph schema migrator (REL-13, book §13).

Version-stamps a KG snapshot JSON to the current ``kg_schema`` version. KG
migrations are explicit; when a snapshot cannot be migrated safely the operator
falls back to ``opencontext index`` (rebuild from source) — surfaced as an
actionable note rather than a silent data rewrite.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.migration.harness import MigrationError, MigrationPlan

TARGET_KG_SCHEMA = "opencontext.kg.v2"


class KGMigrator:
    """Migrate a KG snapshot document to the current KG schema version."""

    domain = "kg"

    def _load(self, target: Path) -> dict[str, object]:
        if not target.is_file():
            raise MigrationError(
                f"KG migration failed: {target} not found.\n"
                f"Suggested fix: run `opencontext index .` to (re)build the graph from source."
            )
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MigrationError(
                f"KG migration failed: {target} is not readable JSON ({exc}).\n"
                f"Suggested fix: rebuild with `opencontext index .`."
            ) from exc
        if not isinstance(data, dict):
            raise MigrationError("KG migration failed: snapshot must be a JSON object.")
        return data

    def plan(self, target: Path) -> MigrationPlan:
        data = self._load(target)
        current = str(data.get("schema_version", "opencontext.kg.v1"))
        if current == TARGET_KG_SCHEMA:
            return MigrationPlan(
                domain=self.domain,
                from_version=current,
                to_version=current,
                notes=["KG snapshot already at the current schema version"],
            )
        return MigrationPlan(
            domain=self.domain,
            from_version=current,
            to_version=TARGET_KG_SCHEMA,
            added=[f"schema_version: {TARGET_KG_SCHEMA}"],
            notes=["if migration is unsafe, rebuild from source with `opencontext index .`"],
        )

    def apply(self, target: Path, plan: MigrationPlan) -> None:
        data = self._load(target)
        data["schema_version"] = TARGET_KG_SCHEMA
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")


__all__ = ["TARGET_KG_SCHEMA", "KGMigrator"]
