"""Tests for ContradictionDetector — 4 cases."""

from __future__ import annotations

from datetime import UTC, datetime

from opencontext_core.memory.contradictions import ContradictionDetector
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord


def make_record(
    record_id: str,
    key: str = "test:key",
    content: str = "some content",
    confidence: float = 0.9,
) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=record_id,
        layer=MemoryLayer.EPISODIC,
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


def test_same_key_different_content_detected() -> None:
    detector = ContradictionDetector()
    new_rec = make_record(
        "new", key="proc:auth", content="auth needs token refresh", confidence=0.9
    )
    existing = [
        make_record("old", key="proc:auth", content="auth never needs refresh", confidence=0.5)
    ]
    contradicted = detector.detect(new_rec, existing)
    assert "old" in contradicted


def test_same_key_same_content_no_contradiction() -> None:
    detector = ContradictionDetector()
    new_rec = make_record("new", key="proc:auth", content="auth needs token", confidence=0.9)
    existing = [make_record("old", key="proc:auth", content="auth needs token", confidence=0.5)]
    contradicted = detector.detect(new_rec, existing)
    assert contradicted == []


def test_different_key_no_contradiction() -> None:
    detector = ContradictionDetector()
    new_rec = make_record("new", key="proc:auth", content="auth needs token refresh")
    existing = [make_record("old", key="proc:db", content="different content")]
    contradicted = detector.detect(new_rec, existing)
    assert contradicted == []


def test_empty_existing_returns_empty() -> None:
    detector = ContradictionDetector()
    new_rec = make_record("new")
    contradicted = detector.detect(new_rec, [])
    assert contradicted == []
