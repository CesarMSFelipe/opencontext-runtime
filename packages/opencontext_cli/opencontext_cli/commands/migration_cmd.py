"""CLI for `version` + `*/migrate` (REL-13) and the release acceptance verdict.

Thin wrappers over :mod:`opencontext_core.migration` (dry-run + backups + actionable
errors) and :mod:`opencontext_core.operating_model.release_gate`. Each migrate
command shares one harness so config/kg/memory/session behave identically.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from opencontext_core.migration import (
    ConfigMigrator,
    KGMigrator,
    MemoryMigrator,
    MigrationError,
    Migrator,
    SessionMigrator,
    aggregate_versions,
    audit_memory,
    run_migration,
)

_MIGRATORS: dict[str, tuple[Callable[[], Migrator], str]] = {
    "config": (ConfigMigrator, "opencontext.yaml"),
    "kg": (KGMigrator, ".opencontext/kg.json"),
    "memory": (MemoryMigrator, ".opencontext/memory.json"),
    "session": (SessionMigrator, ".opencontext/session.json"),
}


def add_migrate_subparser(group_sub: Any, domain: str, *, extras: tuple[str, ...] = ()) -> None:
    """Add a ``migrate`` subcommand (and any domain extras) to a command group."""
    default_target = _MIGRATORS[domain][1]
    migrate = group_sub.add_parser("migrate", help=f"Migrate {domain} data to the current schema.")
    migrate.add_argument("target", nargs="?", default=default_target, help="File to migrate.")
    migrate.add_argument("--dry-run", action="store_true", help="Print the plan and write nothing.")
    migrate.add_argument(
        "--no-backup", action="store_true", help="Skip the automatic pre-write backup."
    )
    if "audit" in extras:
        au = group_sub.add_parser("audit", help="Read-only memory audit (counts).")
        au.add_argument("target", nargs="?", default=_MIGRATORS["memory"][1])


def handle_migrate(domain: str, args: Any) -> int:
    """Run a per-domain migration with dry-run + backup; return an exit code."""
    migrator_cls, default_target = _MIGRATORS[domain]
    target = Path(getattr(args, "target", None) or default_target)
    try:
        result = run_migration(
            migrator_cls(),
            target,
            dry_run=getattr(args, "dry_run", False),
            backup=not getattr(args, "no_backup", False),
        )
    except MigrationError as exc:
        print(str(exc))
        return 1
    if result.dry_run:
        print(result.plan.render())
        return 0
    print(
        json.dumps(
            {
                "applied": result.applied,
                "message": result.message,
                "backup_path": result.backup_path,
                "to_version": result.plan.to_version,
            },
            indent=2,
        )
    )
    return 0


def handle_memory_audit(args: Any) -> int:
    """Print read-only memory audit counts (book §14)."""
    target = Path(getattr(args, "target", None) or _MIGRATORS["memory"][1])
    try:
        print(json.dumps(audit_memory(target), indent=2))
    except MigrationError as exc:
        print(str(exc))
        return 1
    return 0


def handle_version() -> int:
    """Emit the aggregate runtime/schema version block (book §8)."""
    print(json.dumps(aggregate_versions(), indent=2))
    return 0


__all__ = [
    "add_migrate_subparser",
    "handle_memory_audit",
    "handle_migrate",
    "handle_version",
]
