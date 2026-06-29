"""Config schema migrator: opencontext.yaml v1 -> v2 (REL-13, book §9).

Real, conservative migration: bumps the ``version`` key to 2 (which opts the file
into the v2 resolution path) and never removes or rewrites the user's existing
settings. A v2 (or newer) file is a no-op. Backups are taken by the harness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from opencontext_core.migration.harness import MigrationError, MigrationPlan

TARGET_VERSION = 2


class ConfigMigrator:
    """Migrate an ``opencontext.yaml`` to the current config schema version."""

    domain = "config"

    def _load(self, target: Path) -> dict[str, Any]:
        if not target.is_file():
            raise MigrationError(
                f"Config migration failed: {target} not found.\n"
                f"Suggested fix: run `opencontext init` first, or pass the correct path."
            )
        try:
            data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise MigrationError(
                f"Config migration failed: {target} is not valid YAML ({exc}).\n"
                f"Suggested fix: repair the YAML or restore from a backup."
            ) from exc
        if not isinstance(data, dict):
            raise MigrationError(
                f"Config migration failed: {target} must be a YAML mapping at the top level."
            )
        return data

    def plan(self, target: Path) -> MigrationPlan:
        data = self._load(target)
        current = int(data.get("version", 1) or 1)
        if current >= TARGET_VERSION:
            return MigrationPlan(
                domain=self.domain,
                from_version=f"v{current}",
                to_version=f"v{current}",
                notes=["already at the current config schema version"],
            )
        return MigrationPlan(
            domain=self.domain,
            from_version=f"v{current}",
            to_version=f"v{TARGET_VERSION}",
            added=[f"version: {TARGET_VERSION}"],
            notes=["v2 opts the config into the v2 resolution path; existing keys preserved"],
        )

    def apply(self, target: Path, plan: MigrationPlan) -> None:
        data = self._load(target)
        data["version"] = TARGET_VERSION
        target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


__all__ = ["TARGET_VERSION", "ConfigMigrator"]
