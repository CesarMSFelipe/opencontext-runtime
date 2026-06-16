"""Tests that ContradictionDetector runs on every write before persist.

For each contradicted prior record id, the store MUST call
contradict(id, evidence) so superseded/conflicting knowledge is down-weighted
rather than silently duplicated (spec: Contradiction Detection Runs on Every
Write Before Persist).
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord


def make_record(
    record_id: str,
    key: str = "auth:login",
    content: str = "use cookie session",
    layer: MemoryLayer = MemoryLayer.SEMANTIC,
    confidence: float = 0.9,
) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=record_id,
        layer=layer,
        key=key,
        content=content,
        confidence=confidence,
        source_refs=[],
        decay_policy=DecayPolicy(enabled=False),
        tags=[],
        linked_nodes=[],
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def store() -> LocalMemoryStore:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield LocalMemoryStore(Path(tmpdir) / "mem.db")


def test_conflicting_write_decays_prior_record(store: LocalMemoryStore) -> None:
    prior = make_record("old", key="auth:login", content="use cookie session", confidence=0.9)
    store.write(prior)

    new = make_record("new", key="auth:login", content="use bearer token", confidence=0.4)
    store.write(new)

    recs = store._backend.get_by_key("auth:login")
    old_updated = next((r for r in recs if r.id == "old"), None)
    assert old_updated is not None
    # confidence decayed by contradict (0.9 - 0.2)
    assert old_updated.confidence < 0.9
    assert len(old_updated.contradicted_by) == 1
    # both records remain retrievable (no silent overwrite/data loss)
    assert any(r.id == "new" for r in recs)


def test_non_conflicting_write_does_not_decay(store: LocalMemoryStore) -> None:
    prior = make_record("old", key="auth:login", content="use cookie session", confidence=0.9)
    store.write(prior)

    # Different key — no contradiction
    new = make_record("new", key="auth:logout", content="clear cookie", confidence=0.4)
    store.write(new)

    recs = store._backend.get_by_key("auth:login")
    old_updated = next((r for r in recs if r.id == "old"), None)
    assert old_updated is not None
    assert old_updated.confidence == 0.9
    assert old_updated.contradicted_by == []


def test_same_content_write_does_not_decay(store: LocalMemoryStore) -> None:
    prior = make_record("old", key="auth:login", content="use cookie session", confidence=0.9)
    store.write(prior)

    # Same key + same content -> not a contradiction even with confidence diff
    new = make_record("new", key="auth:login", content="use cookie session", confidence=0.4)
    store.write(new)

    recs = store._backend.get_by_key("auth:login")
    old_updated = next((r for r in recs if r.id == "old"), None)
    assert old_updated is not None
    assert old_updated.confidence == 0.9
    assert old_updated.contradicted_by == []


def test_first_write_has_no_contradiction(store: LocalMemoryStore) -> None:
    # writing into an empty store must not raise and must persist
    rec = make_record("first", key="auth:login", content="use cookie session")
    returned = store.write(rec)
    assert returned == "first"
    recs = store._backend.get_by_key("auth:login")
    assert any(r.id == "first" for r in recs)
