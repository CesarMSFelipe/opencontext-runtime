"""Per-kind memory review lifecycle: flag stale high-stakes beliefs, confirm/correct.

Decay protects frequently-used memory, so a trusted-but-stale decision is exactly
what never gets evicted. This lifecycle re-surfaces high-stakes kinds for
re-confirmation instead of letting them drift silently.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from opencontext_core.memory.graph import REVIEW_INTERVAL_DAYS, LocalMemoryStore
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord


def _store(tmp_path: Path) -> LocalMemoryStore:
    return LocalMemoryStore(tmp_path / "memory.db")


def _rec(rid: str, kind: str, age_days: int) -> MemoryRecord:
    ts = datetime.now(tz=UTC) - timedelta(days=age_days)
    return MemoryRecord(
        id=rid,
        layer=MemoryLayer.SEMANTIC,
        key=f"k:{rid}",
        content=f"belief {rid}",
        confidence=0.8,
        source_refs=[],
        decay_policy=DecayPolicy(enabled=True),
        tags=[f"kind:{kind}"],
        linked_nodes=[],
        created_at=ts,
        updated_at=ts,
        valid_from=ts,
    )


def test_review_due_flags_only_stale_high_stakes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    old = REVIEW_INTERVAL_DAYS + 10
    store._backend.store(_rec("d-old", "decision", old))  # due
    store._backend.store(_rec("c-old", "constraint", old))  # due
    store._backend.store(_rec("f-old", "fact", old))  # low-stakes -> not due
    store._backend.store(_rec("d-new", "decision", 1))  # recent -> not due

    due_ids = {r.id for r in store.review_due()}
    assert due_ids == {"d-old", "c-old"}


def test_mark_reviewed_clears_due_and_reinforces(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store._backend.store(_rec("d1", "decision", REVIEW_INTERVAL_DAYS + 5))
    assert {r.id for r in store.review_due()} == {"d1"}

    assert store.mark_reviewed("d1") is True

    assert store.review_due() == []  # clock reset -> no longer due
    assert store.get("d1").confidence > 0.8  # a review is positive evidence
    assert store.mark_reviewed("missing") is False


def test_supersede_replaces_stale_belief(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store._backend.store(_rec("d1", "decision", REVIEW_INTERVAL_DAYS + 5))

    old = store.get("d1")
    now = datetime.now(tz=UTC)
    replacement = old.model_copy(
        update={
            "id": "d2",
            "content": "corrected belief",
            "created_at": now,
            "updated_at": now,
            "valid_from": now,
        }
    )
    store.supersede("d1", replacement)

    assert store.get("d1").invalid_at is not None  # old belief retired, not deleted
    assert store.get("d2").content == "corrected belief"
    # The replacement is fresh, so nothing is due anymore.
    assert store.review_due() == []


def test_maintain_reports_reviews_due(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store._backend.store(_rec("d1", "decision", REVIEW_INTERVAL_DAYS + 5))
    assert store.maintain().reviews_due == 1
