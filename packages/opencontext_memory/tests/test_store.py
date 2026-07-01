"""Tests for the canonical ``opencontext_memory.store.MemoryStore``.

Per strict-TDD: this file is the source of truth for the MemoryStore contract.
``store/sqlite.py`` is written to satisfy these tests.

T2.6 — ``test_REQ_OMS_001_*`` written first (RED). ``store/sqlite.py`` and
``store/write_queue.py`` land in the same apply batch to turn it GREEN.
"""

from __future__ import annotations

from opencontext_memory import MemoryStore, Observation

# ---------------------------------------------------------------------------
# REQ-OMS-001 — write inserts row + FTS row + BM25 search (T2.6)
# ---------------------------------------------------------------------------


def test_REQ_OMS_001_write_inserts_row_and_fts_and_search_bm25(store_db) -> None:
    """A write inserts into ``observations`` AND ``observations_fts``; search
    ranks hits by FTS5 BM25 with the most relevant row first."""
    store = MemoryStore.open(store_db)

    # Single write: row in observations + matching FTS row.
    first_id = store.write(
        Observation(
            session_id="sess-1",
            type="decision",
            title="T",
            content="C",
            project="P",
            topic_key="intro/one",
        )
    )
    assert first_id >= 1

    with store._connect() as conn:
        row = conn.execute(
            "SELECT title, content, project, topic_key FROM observations WHERE id = ?",
            (first_id,),
        ).fetchone()
        assert tuple(row) == ("T", "C", "P", "intro/one")

        fts_row = conn.execute(
            "SELECT title FROM observations_fts WHERE rowid = ?",
            (first_id,),
        ).fetchone()
        assert tuple(fts_row) == ("T",)

    # BM25 ranking: "login" matches the bug-fix row over auth/logout rows.
    store.write(
        Observation(
            session_id="sess-1",
            type="decision",
            title="Fix login bug",
            content="users get 500 on /login POST",
            project="P",
        )
    )
    store.write(
        Observation(
            session_id="sess-1",
            type="decision",
            title="Auth refactor",
            content="extract auth middleware",
            project="P",
        )
    )
    store.write(
        Observation(
            session_id="sess-1",
            type="decision",
            title="Logout cleanup",
            content="delete stale logout tokens",
            project="P",
        )
    )

    hits = store.search("login", limit=2)
    assert hits, "search must return at least one hit"
    assert hits[0]["title"] == "Fix login bug"


# ---------------------------------------------------------------------------
# T2.10 — migrations apply idempotently (REDo, then GREEN with migrations.py)
# ---------------------------------------------------------------------------


def test_migrations_apply_idempotent(store_db) -> None:
    """``opencontext_memory.store.migrations.migrate(flag=False)`` runs against
    an existing DB without raising AND can be re-invoked safely
    (idempotency contract). Production code lands in T2.9 to satisfy this test.
    """
    from opencontext_memory.store.migrations import migrate

    # First open + first migrate: fresh DB, schema applies via schema.sql.
    store = MemoryStore.open(store_db)
    migrate(store_db, flag=False)
    # Second migration on the same DB must NOT raise (idempotency).
    migrate(store_db, flag=False)

    # Sanity: a write still works after a 2-pass migration.
    obs_id = store.write(
        Observation(
            session_id="s-1",
            type="decision",
            title="Post-migration",
            content="ok",
            project="P",
        )
    )
    assert obs_id >= 1
