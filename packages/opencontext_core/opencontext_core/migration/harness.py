"""Migration harness: uniform dry-run, backup, and actionable errors (REL-13).

One harness drives every per-domain migrator (config / kg / memory / session) so
they all share the same UX (book §29): a ``--dry-run`` that prints the plan and
writes nothing, an automatic backup before any real write, and migrations that
NEVER silently promote or delete data — deprecated records are marked
stale/superseded, not erased (book §11/§14).
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class MigrationError(Exception):
    """Raised with an actionable message when a migration cannot proceed (book §29)."""


class MigrationPlan(BaseModel):
    """The computed shape of a migration — printed verbatim by ``--dry-run``."""

    model_config = ConfigDict(extra="forbid")

    domain: str = Field(description="config | kg | memory | session.")
    from_version: str
    to_version: str
    added: list[str] = Field(default_factory=list)
    renamed: list[str] = Field(default_factory=list, description="'old -> new' strings.")
    removed: list[str] = Field(default_factory=list)
    marked_stale: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @property
    def is_noop(self) -> bool:
        return not (self.added or self.renamed or self.removed or self.marked_stale)

    def render(self) -> str:
        lines = [f"{self.domain} migration {self.from_version} -> {self.to_version}", ""]
        for label, rows in (
            ("Added", self.added),
            ("Renamed", self.renamed),
            ("Removed", self.removed),
            ("Marked stale/superseded", self.marked_stale),
        ):
            lines.append(f"{label}:")
            lines.extend(f"  {r}" for r in rows) if rows else lines.append("  none")
        for note in self.notes:
            lines.append(f"note: {note}")
        return "\n".join(lines)


class MigrationResult(BaseModel):
    """The outcome of (optionally) applying a :class:`MigrationPlan`."""

    model_config = ConfigDict(extra="forbid")

    plan: MigrationPlan
    dry_run: bool
    applied: bool
    backup_path: str | None = None
    message: str = ""


@runtime_checkable
class Migrator(Protocol):
    """A per-domain migrator: compute a plan, then apply it to a target path."""

    domain: str

    def plan(self, target: Path) -> MigrationPlan: ...
    def apply(self, target: Path, plan: MigrationPlan) -> None: ...


def backup_path_for(target: Path) -> Path:
    """A timestamped sibling backup path: ``name.ext.bak-YYYYmmdd-HHMMSS``."""
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return target.with_name(f"{target.name}.bak-{ts}")


def make_backup(target: Path) -> Path | None:
    """Copy a file/dir to a timestamped backup; ``None`` when nothing to back up."""
    if not target.exists():
        return None
    dest = backup_path_for(target)
    if target.is_dir():
        shutil.copytree(target, dest)
    else:
        shutil.copy2(target, dest)
    return dest


def run_migration(
    migrator: Migrator,
    target: Path | str,
    *,
    dry_run: bool = False,
    backup: bool = True,
) -> MigrationResult:
    """Drive one migrator with uniform dry-run + backup semantics.

    Dry-run computes and returns the plan WITHOUT touching disk. A real run backs
    the target up first (unless ``backup=False``) then applies; a no-op plan never
    writes and never backs up.
    """
    target = Path(target)
    plan = migrator.plan(target)

    if dry_run:
        return MigrationResult(
            plan=plan, dry_run=True, applied=False, message="dry-run: nothing written"
        )

    if plan.is_noop:
        return MigrationResult(
            plan=plan, dry_run=False, applied=False, message="already up to date"
        )

    backup_loc = make_backup(target) if backup else None
    migrator.apply(target, plan)
    return MigrationResult(
        plan=plan,
        dry_run=False,
        applied=True,
        backup_path=str(backup_loc) if backup_loc else None,
        message="migration applied",
    )


__all__ = [
    "MigrationError",
    "MigrationPlan",
    "MigrationResult",
    "Migrator",
    "backup_path_for",
    "make_backup",
    "run_migration",
]
