"""Session migrator (REL-13, book §11).

Old sessions must remain readable. This migrator version-stamps a session record
JSON to the current session schema; the harness backs the file up first so the
original is never mutated without a backup (book §11/§24).
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.migration.harness import MigrationError, MigrationPlan

TARGET_SESSION_SCHEMA = "opencontext.session.v1"


class SessionMigrator:
    """Migrate one session record JSON to the current session schema version."""

    domain = "session"

    def _load(self, target: Path) -> dict[str, object]:
        if not target.is_file():
            raise MigrationError(
                f"Session migration failed: {target} not found.\n"
                f"Suggested fix: list sessions with `opencontext session list` and retry."
            )
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MigrationError(
                f"Session migration failed: {target} is not readable JSON ({exc})."
            ) from exc
        if not isinstance(data, dict):
            raise MigrationError("Session migration failed: session record must be a JSON object.")
        return data

    def plan(self, target: Path) -> MigrationPlan:
        data = self._load(target)
        current = str(data.get("schema_version", "opencontext.session.v0"))
        if current == TARGET_SESSION_SCHEMA:
            return MigrationPlan(
                domain=self.domain,
                from_version=current,
                to_version=current,
                notes=["session already at the current schema version"],
            )
        return MigrationPlan(
            domain=self.domain,
            from_version=current,
            to_version=TARGET_SESSION_SCHEMA,
            added=[f"schema_version: {TARGET_SESSION_SCHEMA}"],
            notes=["original is backed up before write; old sessions remain readable"],
        )

    def apply(self, target: Path, plan: MigrationPlan) -> None:
        data = self._load(target)
        data["schema_version"] = TARGET_SESSION_SCHEMA
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")


__all__ = ["TARGET_SESSION_SCHEMA", "SessionMigrator"]
