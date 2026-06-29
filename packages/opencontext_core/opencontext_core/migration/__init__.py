"""Migration tooling (REL-13, OC-RELEASE-001 §9-14): dry-run + backups.

A single harness drives per-domain migrators (config / kg / memory / session)
with uniform ``--dry-run``, automatic backups, and actionable errors. Migrations
never silently promote or delete data (book §11/§14).
"""

from opencontext_core.migration.config import ConfigMigrator
from opencontext_core.migration.harness import (
    MigrationError,
    MigrationPlan,
    MigrationResult,
    Migrator,
    make_backup,
    run_migration,
)
from opencontext_core.migration.kg import KGMigrator
from opencontext_core.migration.memory import MemoryMigrator, audit_memory
from opencontext_core.migration.session import SessionMigrator
from opencontext_core.migration.versions import aggregate_versions

__all__ = [
    "ConfigMigrator",
    "KGMigrator",
    "MemoryMigrator",
    "MigrationError",
    "MigrationPlan",
    "MigrationResult",
    "Migrator",
    "SessionMigrator",
    "aggregate_versions",
    "audit_memory",
    "make_backup",
    "run_migration",
]
