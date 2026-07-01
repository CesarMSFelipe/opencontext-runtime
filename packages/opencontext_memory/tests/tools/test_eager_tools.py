"""Tests for the eager memory tools (PR2.b / PR2.c).

Per strict-TDD: this file is the source of truth for ``mem_save``. The
``tools/mem_save.py`` module is written to satisfy these tests.

T2.21 — ``test_REQ_OMT_001_save_*`` written first (RED). ``tools/mem_save.py``
lands in the same apply batch to turn it GREEN.

REQ-OMT-001 — mem_save returns a :class:`SaveReceipt` containing
``receipt``, ``judgment_required: bool``, and ``candidates: list[CandidateEnvelope]``.
"""

from __future__ import annotations

import re

import pytest
from opencontext_memory import MemoryStore, Observation
from opencontext_memory.tools import mem_save as mem_save_mod


def _make_store(tmp_path) -> MemoryStore:
    return MemoryStore.open(tmp_path / "memory.sqlite3")


# ---------------------------------------------------------------------------
# REQ-OMT-001 — mem_save happy path (T2.21)
# ---------------------------------------------------------------------------


def test_REQ_OMT_001_save_no_candidates_returns_clean_receipt(store_db) -> None:
    """First save into an empty store: no BM25 hit clears the floor, so
    ``judgment_required`` is False and the receipt carries the new row id."""
    store = _make_store(store_db)
    receipt = mem_save_mod.mem_save(
        store=store,
        session_id="sess-1",
        project="P",
        title="Fix login bug",
        content="users get 500 on POST /login",
        type="decision",
    )

    assert receipt.judgment_required is False
    assert receipt.candidates == []
    assert receipt.receipt.id >= 1
    assert receipt.receipt.title == "Fix login bug"


def test_REQ_OMT_001_save_with_conflict_returns_envelope_with_judgment_id(store_db) -> None:
    """When a near-duplicate exists, ``judgment_required`` is True AND each
    candidate has a ``judgment_id`` matching the correlation-handle pattern
    AND a ``pending`` relation row is inserted in ``memory_relations``.
    """
    store = _make_store(store_db)

    # Seed a near-duplicate so BM25 matches above the floor.
    store.write(
        Observation(
            session_id="sess-1",
            title="Fix login bug",
            content="users get 500 on POST /login",
            project="P",
            type="decision",
        )
    )

    receipt = mem_save_mod.mem_save(
        store=store,
        session_id="sess-2",
        project="P",
        title="Login 500 again",
        content="users still get 500 on POST /login",
        type="decision",
    )

    assert receipt.judgment_required is True
    assert len(receipt.candidates) >= 1
    cand = receipt.candidates[0]
    assert re.match(r"^rel-[0-9a-f]{8,}$", cand.judgment_id), (
        f"judgment_id {cand.judgment_id!r} does not match ^rel-[0-9a-f]{(8,)}$"
    )
    assert cand.judgment_status == "pending"

    # And the pending relation row is actually persisted.
    with store._connect() as conn:
        row = conn.execute(
            "SELECT relation, judgment_status FROM memory_relations WHERE judgment_id = ?",
            (cand.judgment_id,),
        ).fetchone()
    assert row is not None
    assert row["judgment_status"] == "pending"


def test_REQ_OMT_001_save_rejects_missing_content(store_db) -> None:
    """Empty content is a hard error (matches the spec's "invalid" branch)."""
    store = _make_store(store_db)

    with pytest.raises(ValueError, match=r"content_required"):
        mem_save_mod.mem_save(
            store=store,
            session_id="sess-1",
            project="P",
            title="t",
            content="",
            type="decision",
        )


def test_REQ_OMT_001_save_persists_observation_with_given_fields(store_db) -> None:
    """Triangulation: a successful save lands in ``observations`` with the
    supplied ``title``, ``content``, ``project``, and ``type`` so a later
    ``mem_get_observation`` would find it.
    """
    store = _make_store(store_db)
    receipt = mem_save_mod.mem_save(
        store=store,
        session_id="sess-1",
        project="P",
        title="Auth refactor",
        content="extract auth middleware into its own module",
        type="decision",
    )

    with store._connect() as conn:
        row = conn.execute(
            "SELECT title, content, project, type FROM observations WHERE id = ?",
            (receipt.receipt.id,),
        ).fetchone()
    assert dict(row) == {
        "title": "Auth refactor",
        "content": "extract auth middleware into its own module",
        "project": "P",
        "type": "decision",
    }
