"""Tests for the canonical ``memory_relations`` table helpers.

Per strict-TDD: this file is the source of truth for the relations contract.
``store/relations.py`` is written to satisfy these tests.

T2.16 — ``test_REQ_OMS_004_*`` written first (RED). ``store/relations.py``
lands in the same apply batch to turn it GREEN.

REQ-OMS-004 — Memory Relations Table
    The store SHALL include a ``memory_relations`` table with columns: ``id``,
    ``source_id``, ``target_id``, ``relation`` (7-verb enum), ``judgment_status``
    (4-state enum), ``marked_by_actor``, ``confidence``, ``reasoning``,
    ``model``, ``judgment_id``, ``created_at``. Insertion with an unknown verb
    SHALL raise ``ValueError("invalid_relation_verb:<verb>")``.
"""

from __future__ import annotations

import re

import pytest
from opencontext_memory import MemoryStore, Observation
from opencontext_memory.store import relations
from opencontext_memory.store.relations import JudgmentStatuses, RelationVerbs

# ---------------------------------------------------------------------------
# REQ-OMS-004 — relations table accepts 7 verbs x 4 statuses (T2.16)
# ---------------------------------------------------------------------------


def test_REQ_OMS_004_verbs_and_statuses_enums_have_expected_cardinality() -> None:
    """The enums are the source of truth for what the table accepts.

    7 verbs and 4 statuses must match the schema CHECK constraints so the
    CHECK constraint never trips an in-process insert.
    """
    assert {v.value for v in RelationVerbs} == {
        "related",
        "compatible",
        "scoped",
        "conflicts_with",
        "supersedes",
        "not_conflict",
    }, "RelationVerbs must enumerate exactly the 7 spec'd verbs"

    assert {s.value for s in JudgmentStatuses} == {
        "pending",
        "judged",
        "orphaned",
        "ignored",
    }, "JudgmentStatuses must enumerate exactly the 4 spec'd states"


def test_REQ_OMS_004_insert_round_trip_writes_pending_row(store_db) -> None:
    """A valid insert persists a row with ``judgment_status='pending'`` by
    default and a unique id.
    """
    store = MemoryStore.open(store_db)
    src = store.write(Observation(session_id="sess-1", title="S", content="S", project="P"))
    tgt = store.write(Observation(session_id="sess-1", title="T", content="T", project="P"))

    row_id = relations.insert(
        store._conn,
        source_id=src,
        target_id=tgt,
        verb=RelationVerbs.RELATED,
        marked_by_actor="user",
    )

    assert row_id >= 1
    with store._connect() as conn:
        row = conn.execute(
            "SELECT source_id, target_id, relation, judgment_status, marked_by_actor, "
            "confidence, judgment_id FROM memory_relations WHERE id = ?",
            (row_id,),
        ).fetchone()
    assert dict(row) == {
        "source_id": src,
        "target_id": tgt,
        "relation": "related",
        "judgment_status": "pending",
        "marked_by_actor": "user",
        "confidence": 1.0,
        "judgment_id": None,
    }


def test_REQ_OMS_004_insert_accepts_all_seven_verbs(store_db) -> None:
    """Triangulation: every verb in the enum persists a valid row (different
    rows, different ``relation`` values). Catches "Fake It" hardcoding.
    """
    store = MemoryStore.open(store_db)
    src = store.write(Observation(session_id="sess-1", title="S", content="S", project="P"))
    tgt = store.write(Observation(session_id="sess-1", title="T", content="T", project="P"))

    seen: set[str] = set()
    for verb in RelationVerbs:
        relations.insert(
            store._conn, source_id=src, target_id=tgt, verb=verb, marked_by_actor="user"
        )
        seen.add(verb.value)

    with store._connect() as conn:
        rows = conn.execute("SELECT DISTINCT relation FROM memory_relations").fetchall()
    assert {r["relation"] for r in rows} == seen == {v.value for v in RelationVerbs}


def test_REQ_OMS_004_insert_rejects_unknown_verb(store_db) -> None:
    """Unknown verbs must raise ``ValueError("invalid_relation_verb:<verb>")``
    and insert nothing.
    """
    store = MemoryStore.open(store_db)
    src = store.write(Observation(session_id="sess-1", title="S", content="S", project="P"))
    tgt = store.write(Observation(session_id="sess-1", title="T", content="T", project="P"))

    with pytest.raises(ValueError, match=r"^invalid_relation_verb:replaces$"):
        relations.insert(
            store._conn,
            source_id=src,
            target_id=tgt,
            verb="replaces",  # type: ignore[arg-type]
            marked_by_actor="user",
        )

    with store._connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM memory_relations").fetchone()["n"]
    assert count == 0, "rejected verb must not insert any row"


def test_REQ_OMS_004_insert_supports_status_and_judgment_id(store_db) -> None:
    """The caller can override ``judgment_status`` and attach a ``judgment_id``
    for the correlation handle pattern used by conflict-surfacing flows.
    """
    store = MemoryStore.open(store_db)
    src = store.write(Observation(session_id="sess-1", title="S", content="S", project="P"))
    tgt = store.write(Observation(session_id="sess-1", title="T", content="T", project="P"))

    row_id = relations.insert(
        store._conn,
        source_id=src,
        target_id=tgt,
        verb=RelationVerbs.SUPERSEDES,
        status=JudgmentStatuses.PENDING,
        marked_by_actor="engram",
        confidence=0.85,
        reasoning="newer API",
        model="claude-haiku-4-5",
        judgment_id="rel-abcdef0123",
    )

    with store._connect() as conn:
        row = conn.execute(
            "SELECT relation, judgment_status, marked_by_actor, confidence, reasoning, "
            "model, judgment_id FROM memory_relations WHERE id = ?",
            (row_id,),
        ).fetchone()
    assert row["relation"] == "supersedes"
    assert row["judgment_status"] == "pending"
    assert row["marked_by_actor"] == "engram"
    assert row["confidence"] == pytest.approx(0.85)
    assert row["reasoning"] == "newer API"
    assert row["model"] == "claude-haiku-4-5"
    assert row["judgment_id"] == "rel-abcdef0123"
    assert re.match(r"^rel-[0-9a-f]{8,}$", row["judgment_id"]), (
        "judgment_id must match the correlation-handle pattern"
    )


def test_REQ_OMS_004_query_by_source_and_target(store_db) -> None:
    """Triangulation: the helper exposes a query path that filters rows by
    ``source_id`` (and ``target_id`` when given). Three rows in, two filter
    outputs out — proves the SQL actually discriminates.
    """
    store = MemoryStore.open(store_db)
    src1 = store.write(Observation(session_id="sess-1", title="A", content="A", project="P"))
    src2 = store.write(Observation(session_id="sess-1", title="B", content="B", project="P"))
    tgt = store.write(Observation(session_id="sess-1", title="T", content="T", project="P"))

    relations.insert(
        store._conn,
        source_id=src1,
        target_id=tgt,
        verb=RelationVerbs.RELATED,
        marked_by_actor="user",
    )
    relations.insert(
        store._conn,
        source_id=src2,
        target_id=tgt,
        verb=RelationVerbs.COMPATIBLE,
        marked_by_actor="user",
    )

    by_src = relations.query_by_source(store._conn, source_id=src1)
    assert len(by_src) == 1
    assert by_src[0]["source_id"] == src1
    assert by_src[0]["relation"] == "related"

    by_pair = relations.query_by_pair(store._conn, source_id=src2, target_id=tgt)
    assert len(by_pair) == 1
    assert by_pair[0]["relation"] == "compatible"

    unrelated = relations.query_by_source(store._conn, source_id=9999)
    assert unrelated == [], "no rows for an unknown source_id"
