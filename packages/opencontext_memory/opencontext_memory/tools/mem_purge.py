"""mem_purge — remove ALL managed memory state from the store (MEM-008).

The uninstall-grade wipe: observations (plus their FTS mirror), relations and
sessions are all deleted. Idempotent — purging an empty store reports zero
removals. Callers own the confirmation gate (the CLI refuses without --yes).
"""

from __future__ import annotations

from typing import Any


def _count(conn: Any, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])


def mem_purge(store: Any) -> dict[str, Any]:
    """Delete every observation, relation and session; returns removal counts."""
    with store._connect() as conn:
        observations = _count(conn, "observations")
        relations = _count(conn, "memory_relations")
        sessions = _count(conn, "sessions")
        conn.execute("DELETE FROM observations")
        # External-content FTS5 tables need the special delete-all command.
        conn.execute("INSERT INTO observations_fts(observations_fts) VALUES('delete-all')")
        conn.execute("DELETE FROM memory_relations")
        conn.execute("DELETE FROM sessions")
    return {
        "purged": True,
        "observations_removed": observations,
        "relations_removed": relations,
        "sessions_removed": sessions,
    }


__all__ = ["mem_purge"]
