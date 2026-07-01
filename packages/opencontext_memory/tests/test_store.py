"""Tests for the canonical ``opencontext_memory.store.MemoryStore``.

Per strict-TDD: this file is the source of truth for the MemoryStore contract.
``store/sqlite.py`` is written to satisfy these tests.

T2.6 — ``test_REQ_OMS_001_*`` written first (RED). ``store/sqlite.py`` and
``store/write_queue.py`` land in the same apply batch to turn it GREEN.

T2.8 — ``test_REQ_OMS_002_*`` (topic-key upsert) and ``test_REQ_OMS_003_*``
(soft/hard delete) added once ``write()`` proves stable. ``delete()`` is the
new method on ``MemoryStore`` introduced to satisfy REQ-OMS-003.
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


# ---------------------------------------------------------------------------
# REQ-OMS-002 — topic-key upsert bumps ``revision_count`` (T2.8)
# ---------------------------------------------------------------------------


def test_REQ_OMS_002_topic_key_matches_updates_in_place(store_db) -> None:
    """A second write with the same ``topic_key + project + scope`` updates
    the existing row in place: ``revision_count`` increments and no duplicate
    row is created."""
    store = MemoryStore.open(store_db)

    first_id = store.write(
        Observation(
            session_id="sess-1",
            type="decision",
            title="Initial fix",
            content="first attempt at auth/login-fix",
            project="P",
            topic_key="auth/login-fix",
        )
    )

    second_id = store.write(
        Observation(
            session_id="sess-1",
            type="decision",
            title="Refined fix",
            content="second attempt at auth/login-fix",
            project="P",
            topic_key="auth/login-fix",
        )
    )

    assert second_id == first_id, "upsert returns the existing row id"

    with store._connect() as conn:
        rows = conn.execute(
            "SELECT id, revision_count FROM observations "
            "WHERE topic_key = ? AND project = ? AND scope = ?",
            ("auth/login-fix", "P", "project"),
        ).fetchall()
        assert len(rows) == 1, "no duplicate row is inserted"
        assert rows[0]["id"] == first_id
        assert rows[0]["revision_count"] == 1


def test_REQ_OMS_002_topic_key_absent_inserts_new_row(store_db) -> None:
    """A write with a never-seen ``topic_key`` inserts a fresh row with
    ``revision_count = 0``."""
    store = MemoryStore.open(store_db)

    new_id = store.write(
        Observation(
            session_id="sess-1",
            type="decision",
            title="Logout fix",
            content="stale logout tokens",
            project="P",
            topic_key="auth/logout-fix",
        )
    )
    assert new_id >= 1

    with store._connect() as conn:
        row = conn.execute(
            "SELECT revision_count FROM observations WHERE id = ?", (new_id,)
        ).fetchone()
        assert row["revision_count"] == 0


def test_REQ_OMS_002_upsert_updates_title_and_content(store_db) -> None:
    """On upsert the existing row's ``title`` and ``content`` are replaced by
    the new observation (so callers can use the topic key as an in-place
    revision handle)."""
    store = MemoryStore.open(store_db)

    first_id = store.write(
        Observation(
            session_id="sess-1",
            type="decision",
            title="v1",
            content="v1 body",
            project="P",
            topic_key="evolving/decision",
        )
    )

    store.write(
        Observation(
            session_id="sess-1",
            type="decision",
            title="v2",
            content="v2 body",
            project="P",
            topic_key="evolving/decision",
        )
    )

    with store._connect() as conn:
        row = conn.execute(
            "SELECT title, content FROM observations WHERE id = ?", (first_id,)
        ).fetchone()
        assert row["title"] == "v2"
        assert row["content"] == "v2 body"


# ---------------------------------------------------------------------------
# REQ-OMS-003 — soft delete hides from search; hard delete removes row (T2.8)
# ---------------------------------------------------------------------------


def test_REQ_OMS_003_soft_delete_hides_from_search(store_db) -> None:
    """``store.delete(id)`` stamps ``deleted_at``; the row drops out of
    ``store.search`` results but remains in the table."""
    store = MemoryStore.open(store_db)

    obs_id = store.write(
        Observation(
            session_id="sess-1",
            type="decision",
            title="Auth refactor",
            content="extract auth middleware",
            project="P",
        )
    )

    # Pre-condition: the row is searchable.
    hits = store.search("auth", limit=10)
    assert any(h["id"] == obs_id for h in hits), "row must appear before delete"

    store.delete(obs_id)

    # Post-condition: the row is hidden from search.
    hits_after = store.search("auth", limit=10)
    assert all(h["id"] != obs_id for h in hits_after), "soft-deleted row hidden"

    # And the row is still present in the table with ``deleted_at`` stamped.
    with store._connect() as conn:
        row = conn.execute(
            "SELECT deleted_at FROM observations WHERE id = ?", (obs_id,)
        ).fetchone()
        assert row is not None, "soft-deleted row still in the table"
        assert row["deleted_at"] is not None


def test_REQ_OMS_003_hard_delete_removes_row_and_fts(store_db) -> None:
    """``store.delete(id, hard=True)`` removes the row outright, including
    its FTS mirror."""
    store = MemoryStore.open(store_db)

    obs_id = store.write(
        Observation(
            session_id="sess-1",
            type="decision",
            title="Ephemeral",
            content="transient note",
            project="P",
        )
    )

    store.delete(obs_id, hard=True)

    with store._connect() as conn:
        row = conn.execute(
            "SELECT id FROM observations WHERE id = ?", (obs_id,)
        ).fetchone()
        assert row is None, "hard-deleted row removed from observations"

        fts_row = conn.execute(
            "SELECT rowid FROM observations_fts WHERE rowid = ?", (obs_id,)
        ).fetchone()
        assert fts_row is None, "hard-deleted row removed from observations_fts"

    hits = store.search("Ephemeral", limit=10)
    assert all(h["id"] != obs_id for h in hits)


def test_REQ_OMS_003_soft_delete_is_idempotent(store_db) -> None:
    """Soft-deleting an already soft-deleted row must NOT stomp the original
    ``deleted_at`` timestamp (audit trail preserved)."""
    store = MemoryStore.open(store_db)

    obs_id = store.write(
        Observation(
            session_id="sess-1",
            type="decision",
            title="Audit me",
            content="row to soft-delete twice",
            project="P",
        )
    )

    store.delete(obs_id)
    with store._connect() as conn:
        first = conn.execute(
            "SELECT deleted_at FROM observations WHERE id = ?", (obs_id,)
        ).fetchone()["deleted_at"]

    store.delete(obs_id)
    with store._connect() as conn:
        second = conn.execute(
            "SELECT deleted_at FROM observations WHERE id = ?", (obs_id,)
        ).fetchone()["deleted_at"]

    assert first == second, "second soft-delete does not overwrite the audit stamp"
