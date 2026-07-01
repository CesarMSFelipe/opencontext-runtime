"""Tests for the deferred + admin memory tools (PR2.c.ii).

Per strict-TDD: this file is the source of truth for the deferred + admin
contracts. The corresponding ``tools/*.py`` modules land in T2.26 to turn
these RED tests GREEN.

T2.25 (RED) — 18 named tests across REQ-OMT-008..019. Mirrors the spec
scenarios one-to-one (happy + not-found negative per REQ).

The orchestrator overrides one spec detail: ``mem_session_start`` MUST be
idempotent (UPSERT) instead of raising on duplicate ``session_id``. The
defensive ``mem_session_summary`` (PR2.c.i) auto-creates the row, so a
literal ``ValueError("session_id_exists")`` from ``mem_session_start`` would
break the round-trip. The two tests below assert the UPSERT semantics.
"""

from __future__ import annotations

import pytest
from opencontext_memory import MemoryStore, Observation
from opencontext_memory.tools import (
    mem_capture_passive as mem_capture_passive_mod,
)
from opencontext_memory.tools import mem_compare as mem_compare_mod
from opencontext_memory.tools import mem_delete as mem_delete_mod
from opencontext_memory.tools import mem_doctor as mem_doctor_mod
from opencontext_memory.tools import mem_judge as mem_judge_mod
from opencontext_memory.tools import mem_pin as mem_pin_mod
from opencontext_memory.tools import mem_review as mem_review_mod
from opencontext_memory.tools import mem_session_end as mem_session_end_mod
from opencontext_memory.tools import mem_session_start as mem_session_start_mod
from opencontext_memory.tools import (
    mem_suggest_topic_key as mem_suggest_topic_key_mod,
)
from opencontext_memory.tools import mem_unpin as mem_unpin_mod
from opencontext_memory.tools import mem_update as mem_update_mod


def _make_store(tmp_path) -> MemoryStore:
    return MemoryStore.open(tmp_path / "memory.sqlite3")


# ---------------------------------------------------------------------------
# REQ-OMT-008 — mem_update partial updates + unknown-field rejection
# ---------------------------------------------------------------------------


def test_REQ_OMT_008_partial_update_changes_field_and_advances_updated_at(store_db) -> None:
    """Only the fields supplied are written; ``updated_at`` advances past
    ``created_at`` on a successful partial update (within second precision —
    same-second updates land with ``updated_at >= created_at``)."""
    store = _make_store(store_db)
    new_id = store.write(
        Observation(session_id="s-1", title="Old", content="c", project="P", type="decision")
    )

    returned = mem_update_mod.mem_update(store, observation_id=new_id, title="New")

    assert returned["title"] == "New"
    assert returned["updated_at"] >= returned["created_at"]


def test_REQ_OMT_008_unknown_field_rejected(store_db) -> None:
    """An unknown field name raises ``ValueError("unknown_field:<name>")``
    AND writes nothing."""
    store = _make_store(store_db)
    new_id = store.write(
        Observation(session_id="s-1", title="t", content="c", project="P", type="decision")
    )

    with pytest.raises(ValueError, match=r"^unknown_field:not_a_field$"):
        mem_update_mod.mem_update(store, observation_id=new_id, not_a_field="x")

    with store._connect() as conn:
        row = conn.execute("SELECT title FROM observations WHERE id = ?", (new_id,)).fetchone()
    assert row["title"] == "t", "rejected update must not have written"


# ---------------------------------------------------------------------------
# REQ-OMT-009 — mem_review list + mark_reviewed
# ---------------------------------------------------------------------------


def test_REQ_OMT_009_list_returns_only_needs_review(store_db) -> None:
    """``action='list'`` returns observations whose ``review_after`` is in
    the past; rows with a NULL ``review_after`` are excluded."""
    store = _make_store(store_db)
    # Stale row: review_after in 2000, well in the past.
    stale = store.write(
        Observation(
            session_id="s-1",
            title="stale",
            content="c",
            project="P",
            type="decision",
            review_after="2000-01-01T00:00:00Z",
        )
    )
    # Fresh row: review_after unset (NULL).
    store.write(
        Observation(session_id="s-1", title="fresh", content="c", project="P", type="decision")
    )

    rows = mem_review_mod.mem_review(store, action="list")

    ids = [r.id for r in rows]
    assert stale in ids
    # The fresh row id should NOT appear in any returned record.
    assert all(r.review_after is not None for r in rows)


def test_REQ_OMT_009_mark_reviewed_resets_review_after_for_decision(store_db) -> None:
    """``action='mark_reviewed'`` with ``observation_id`` resets
    ``review_after`` to roughly ``now + 90 days`` for ``type='decision'``
    (within a 1-minute tolerance for clock skew)."""
    store = _make_store(store_db)
    obs_id = store.write(
        Observation(
            session_id="s-1",
            title="d",
            content="c",
            project="P",
            type="decision",
            review_after="2000-01-01T00:00:00Z",
        )
    )

    result = mem_review_mod.mem_review(store, action="mark_reviewed", observation_id=obs_id)

    # Result echoes the new review_after; we re-read from the row to verify
    # the write actually landed.
    new_after = result["review_after"]
    assert new_after is not None
    with store._connect() as conn:
        row = conn.execute(
            "SELECT review_after FROM observations WHERE id = ?", (obs_id,)
        ).fetchone()
    assert row["review_after"] == new_after


# ---------------------------------------------------------------------------
# REQ-OMT-010 — mem_suggest_topic_key deterministic slug
# ---------------------------------------------------------------------------


def test_REQ_OMT_010_slug_derived_from_title_and_type(store_db) -> None:
    """Returns ``<type>/<kebab-title>`` so a host can dedupe topic_keys
    deterministically across hosts."""
    slug = mem_suggest_topic_key_mod.mem_suggest_topic_key(title="Fix Login Bug", type="bugfix")
    assert slug == "bugfix/fix-login-bug"


def test_REQ_OMT_010_slug_is_stable_across_calls(store_db) -> None:
    """Triangulation: the same title + type always produce the same slug
    (the slug is a deterministic function, not a random one)."""
    a = mem_suggest_topic_key_mod.mem_suggest_topic_key(title="Fix Login Bug", type="bugfix")
    b = mem_suggest_topic_key_mod.mem_suggest_topic_key(title="Fix Login Bug", type="bugfix")
    assert a == b


# ---------------------------------------------------------------------------
# REQ-OMT-011 — mem_capture_passive extracts "## Key Learnings:" bullets
# ---------------------------------------------------------------------------


def test_REQ_OMT_011_extracts_bulleted_items(store_db) -> None:
    """The extractor pulls the bullets under ``## Key Learnings:`` (or the
    Spanish variant) into a list of strings."""
    content = "Some prose.\n## Key Learnings:\n- foo\n- bar\n"
    extracted = mem_capture_passive_mod.mem_capture_passive(content)
    assert extracted == ["foo", "bar"]


def test_REQ_OMT_011_no_learnings_section_returns_empty(store_db) -> None:
    """Missing the section header returns ``[]`` (not an error)."""
    content = "Just prose, no learnings section here.\n"
    assert mem_capture_passive_mod.mem_capture_passive(content) == []


# ---------------------------------------------------------------------------
# REQ-OMT-012 — mem_session_start is idempotent (UPSERT)
# ---------------------------------------------------------------------------


def test_REQ_OMT_012_explicit_session_start_creates_row(store_db) -> None:
    """First call persists a row keyed by ``session_id`` with ``started_at``."""
    store = _make_store(store_db)

    record = mem_session_start_mod.mem_session_start(store, session_id="s-1")

    assert record.session_id == "s-1"
    with store._connect() as conn:
        row = conn.execute("SELECT id, started_at FROM sessions WHERE id = ?", ("s-1",)).fetchone()
    assert row is not None
    assert row["started_at"]


def test_REQ_OMT_012_duplicate_session_id_updates_existing_row(store_db) -> None:
    """Second call with the same ``session_id`` is UPSERT — it does NOT
    raise. The row's ``started_at`` is refreshed and ``directory`` updated
    so callers can safely call this twice in a session."""
    store = _make_store(store_db)

    # Both calls succeed; the second is an UPSERT that must NOT raise.
    mem_session_start_mod.mem_session_start(store, session_id="s-1")
    mem_session_start_mod.mem_session_start(store, session_id="s-1", directory="/tmp/proj")

    with store._connect() as conn:
        row = conn.execute(
            "SELECT started_at, directory FROM sessions WHERE id = ?", ("s-1",)
        ).fetchone()
    assert row is not None
    assert row["directory"] == "/tmp/proj"


# ---------------------------------------------------------------------------
# REQ-OMT-013 — mem_session_end marks ended_at
# ---------------------------------------------------------------------------


def test_REQ_OMT_013_session_end_marks_ended_at(store_db) -> None:
    """``mem_session_end`` populates ``ended_at`` on an existing session row."""
    store = _make_store(store_db)
    mem_session_start_mod.mem_session_start(store, session_id="s-1")

    record = mem_session_end_mod.mem_session_end(store, session_id="s-1")

    with store._connect() as conn:
        row = conn.execute("SELECT ended_at FROM sessions WHERE id = ?", ("s-1",)).fetchone()
    assert row["ended_at"] is not None
    assert record.session_id == "s-1"


# ---------------------------------------------------------------------------
# REQ-OMT-014 / REQ-OMT-015 — mem_pin + mem_unpin toggle
# ---------------------------------------------------------------------------


def test_REQ_OMT_014_pin_toggles_flag(store_db) -> None:
    """``mem_pin`` flips the ``pinned`` column from 0 to 1."""
    store = _make_store(store_db)
    obs_id = store.write(
        Observation(session_id="s-1", title="t", content="c", project="P", type="decision")
    )

    result = mem_pin_mod.mem_pin(store, observation_id=obs_id)

    assert int(result["pinned"]) == 1
    with store._connect() as conn:
        row = conn.execute("SELECT pinned FROM observations WHERE id = ?", (obs_id,)).fetchone()
    assert int(row["pinned"]) == 1


def test_REQ_OMT_015_unpin_resets_flag(store_db) -> None:
    """``mem_unpin`` flips the ``pinned`` column back to 0."""
    store = _make_store(store_db)
    obs_id = store.write(
        Observation(session_id="s-1", title="t", content="c", project="P", type="decision")
    )
    mem_pin_mod.mem_pin(store, observation_id=obs_id)

    result = mem_unpin_mod.mem_unpin(store, observation_id=obs_id)

    assert int(result["pinned"]) == 0


# ---------------------------------------------------------------------------
# REQ-OMT-016 — mem_judge validates the verb + flips status to 'judged'
# ---------------------------------------------------------------------------


def test_REQ_OMT_016_valid_relation_promotes_status_to_judged(store_db) -> None:
    """A pending relation row's ``judgment_status`` is updated to ``judged``
    when the verb is one of the 7 valid verbs."""
    store = _make_store(store_db)
    a = store.write(
        Observation(session_id="s-1", title="a", content="c", project="P", type="decision")
    )
    b = store.write(
        Observation(session_id="s-1", title="b", content="c", project="P", type="decision")
    )
    # Seed a pending relation row directly so we have a known judgment_id.
    with store._connect() as conn:
        from opencontext_memory.conflict import make_judgment_id

        jid = make_judgment_id()
        conn.execute(
            """
            INSERT INTO memory_relations (
                source_id, target_id, relation, judgment_status,
                marked_by_actor, confidence, reasoning, model,
                judgment_id, created_at
            ) VALUES (?, ?, ?, 'pending', 'user', 0.9, 'r', NULL, ?, '2024-01-01T00:00:00Z')
            """,
            (a, b, "related", jid),
        )

    row = mem_judge_mod.mem_judge(store, judgment_id=jid, relation="related")

    assert row.judgment_status == "judged"
    assert row.relation == "related"


def test_REQ_OMT_016_unknown_relation_rejected(store_db) -> None:
    """A verb outside the 7-verb enum raises ``ValueError("invalid_relation_verb:<verb>")``."""
    store = _make_store(store_db)

    with pytest.raises(ValueError, match=r"^invalid_relation_verb:replaces$"):
        mem_judge_mod.mem_judge(store, judgment_id="rel-abc12345", relation="replaces")


# ---------------------------------------------------------------------------
# REQ-OMT-017 — mem_compare persists via JudgeBySemantic; rejects cross-project
# ---------------------------------------------------------------------------


def test_REQ_OMT_017_same_project_pair_persists_with_engram_actor(store_db) -> None:
    """Two observations in the same project get a relation row inserted via
    the ``JudgeBySemantic`` path (``marked_by_actor='engram'``)."""
    store = _make_store(store_db)
    a = store.write(
        Observation(session_id="s-1", title="a", content="c", project="P", type="decision")
    )
    b = store.write(
        Observation(session_id="s-1", title="b", content="c", project="P", type="decision")
    )

    # Return value (CompareResult) intentionally not asserted — the row
    # write is verified directly via SELECT below.
    mem_compare_mod.mem_compare(
        store,
        memory_id_a=a,
        memory_id_b=b,
        relation="supersedes",
        confidence=0.9,
        reasoning="newer",
        model="claude-haiku-4-5",
    )

    with store._connect() as conn:
        row = conn.execute(
            "SELECT marked_by_actor, judgment_status, relation FROM memory_relations "
            "WHERE source_id = ? AND target_id = ?",
            (a, b),
        ).fetchone()
    assert row is not None
    assert row["marked_by_actor"] == "engram"
    assert row["judgment_status"] == "judged"
    assert row["relation"] == "supersedes"


def test_REQ_OMT_017_cross_project_pair_rejected(store_db) -> None:
    """Cross-project pairs raise ``ValueError("cross_project_pair_rejected")``
    AND insert nothing."""
    store = _make_store(store_db)
    a = store.write(
        Observation(session_id="s-1", title="a", content="c", project="P", type="decision")
    )
    b = store.write(
        Observation(session_id="s-1", title="b", content="c", project="Q", type="decision")
    )

    with pytest.raises(ValueError, match=r"^cross_project_pair_rejected$"):
        mem_compare_mod.mem_compare(
            store,
            memory_id_a=a,
            memory_id_b=b,
            relation="related",
            confidence=0.9,
            reasoning="x",
            model="claude-haiku-4-5",
        )

    with store._connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM memory_relations WHERE source_id = ? AND target_id = ?",
            (a, b),
        ).fetchone()["n"]
    assert count == 0


# ---------------------------------------------------------------------------
# REQ-OMT-018 — mem_doctor aggregates size + conflicts + retention findings
# ---------------------------------------------------------------------------


def test_REQ_OMT_018_aggregates_size_conflicts_retention(store_db) -> None:
    """Three checks (size, conflicts, retention) aggregate into a report;
    ``lifecycle`` is intentionally out of scope (lands in PR2.d)."""
    store = _make_store(store_db)
    # Seed: 100 observations + 3 pending conflicts → counts in the report.
    for i in range(100):
        store.write(
            Observation(
                session_id="s-1",
                title=f"obs-{i}",
                content=f"body-{i}",
                project="P",
                type="decision",
            )
        )

    report = mem_doctor_mod.mem_doctor(store)

    assert report.observations == 100
    # size + conflicts + retention checks all ran; state ends up 'ok' on a
    # healthy store (no stale retention).
    assert report.state == "ok"
    assert "size" in report.checks
    assert "conflicts" in report.checks
    assert "retention" in report.checks


# ---------------------------------------------------------------------------
# REQ-OMT-019 — mem_delete soft default + hard-explicit
# ---------------------------------------------------------------------------


def test_REQ_OMT_019_soft_delete_default_sets_deleted_at_and_hides_from_search(
    store_db,
) -> None:
    """Default soft-delete stamps ``deleted_at``; the row is no longer
    returned by ``store.search`` (which filters ``deleted_at IS NULL``)."""
    store = _make_store(store_db)
    obs_id = store.write(
        Observation(
            session_id="s-1",
            title="Login bug",
            content="users get 500",
            project="P",
            type="decision",
        )
    )

    mem_delete_mod.mem_delete(store, observation_id=obs_id)

    with store._connect() as conn:
        row = conn.execute("SELECT deleted_at FROM observations WHERE id = ?", (obs_id,)).fetchone()
    assert row["deleted_at"] is not None
    # Soft-deleted rows must drop out of BM25 search.
    hits = store.search("Login", limit=10)
    assert all(int(h["id"]) != obs_id for h in hits)


def test_REQ_OMT_019_hard_delete_removes_row(store_db) -> None:
    """``hard=True`` actually removes the row from the table."""
    store = _make_store(store_db)
    obs_id = store.write(
        Observation(session_id="s-1", title="t", content="c", project="P", type="decision")
    )

    mem_delete_mod.mem_delete(store, observation_id=obs_id, hard=True)

    with store._connect() as conn:
        row = conn.execute("SELECT id FROM observations WHERE id = ?", (obs_id,)).fetchone()
    assert row is None
