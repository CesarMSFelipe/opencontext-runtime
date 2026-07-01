"""opencontext_memory.store.migrations — versioned additive migrations.

PR2.a ships the canonical schema in ``store/schema.sql``; this module is
the version-tracked gate so future schema changes can land as additive
versions without rewriting the existing DDL. Initial version is ``1`` —
the bookkeeping is registered on first call.

``migrate(db_path, *, flag=False)``:

* default (``flag=False``) — additive migrations only
* explicit (``flag=True``) — destructive migrations allowed (none ship yet)

Idempotent — calling on an already-migrated DB is a no-op. Safe to call
from a CLI tool's startup hook or a runtime probe.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

# ponytail: empty registry for now. Schema-version bookkeeping is enough for
# PR2.d's test; future migrations register here as `1: fn, 2: fn, ...`. The
# `flag` parameter is honoured in ``migrate(...)`` so destructive steps can
# be added later without changing the public signature.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {}


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def migrate(db_path: Path, *, flag: bool = False) -> None:
    """Apply pending additive migrations against ``db_path``.

    Creates the ``opencontext_schema_version`` meta table on first call
    and seeds version ``1`` so the bookkeeping is authoritative. Re-invoking
    against the same DB is a no-op (idempotent contract per REQ-OMS-002).
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS opencontext_schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL,
                flag INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        already = {
            int(row["version"])
            for row in conn.execute("SELECT version FROM opencontext_schema_version").fetchall()
        }
        # Seed initial bookkeeping so the version table is never empty
        # on a freshly-migrated DB. The flag is recorded (not enforced)
        # so future audits can see which migrations ran in destructive mode.
        if 1 not in already:
            conn.execute(
                "INSERT INTO opencontext_schema_version (version, applied_at, flag) "
                "VALUES (?, ?, ?)",
                (1, _utcnow_iso(), int(flag)),
            )
        for version, fn in sorted(MIGRATIONS.items()):
            if version in already:
                continue
            fn(conn)
            conn.execute(
                "INSERT INTO opencontext_schema_version (version, applied_at, flag) "
                "VALUES (?, ?, ?)",
                (version, _utcnow_iso(), int(flag)),
            )
        conn.commit()
    finally:
        conn.close()


__all__ = ["MIGRATIONS", "migrate"]
