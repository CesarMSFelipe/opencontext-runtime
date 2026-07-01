"""Tests for Memory v2 conflict detection (PR-009)."""

from __future__ import annotations

from datetime import UTC, datetime

from opencontext_core.memory.v2.conflict import (
    ConflictEnvelopeV2,
    ConflictKindV2,
    detect_contradiction,
)


def _record(
    rec_id: str,
    topic_key: str,
    content: str,
    confidence: float = 0.7,
) -> dict:
    now = datetime.now(tz=UTC)
    return {
        "id": rec_id,
        "topic_key": topic_key,
        "content": content,
        "confidence": confidence,
        "created_at": now,
        "updated_at": now,
    }


def test_REQ_mem_v2_003_contradicts_edge() -> None:
    """Same topic_key, different content, confidence delta > threshold => contradicts."""
    candidate = _record(
        "mem_new", "auth:method", "Auth uses session cookies", confidence=0.95
    )
    existing = [
        _record("mem_old", "auth:method", "Auth uses JWT tokens", confidence=0.5)
    ]
    conflicts = detect_contradiction(candidate, existing, confidence_delta=0.3)
    assert len(conflicts) == 1
    edge: ConflictEnvelopeV2 = conflicts[0]
    assert edge.kind is ConflictKindV2.CONTRADICTS
    assert edge.record_a == "mem_new"
    assert edge.record_b == "mem_old"
    assert edge.confidence > 0.0
    assert edge.judgment_id.startswith("rel-")
    assert len(edge.judgment_id) == len("rel-") + 12  # 12-char hex


def test_detect_contradiction_same_content_is_no_op() -> None:
    """Identical content on the same key is NOT a contradiction."""
    candidate = _record("mem_a", "k", "the same text", confidence=0.9)
    existing = [_record("mem_b", "k", "the same text", confidence=0.9)]
    assert detect_contradiction(candidate, existing) == []


def test_detect_contradiction_different_keys_no_conflict() -> None:
    candidate = _record("mem_a", "k1", "totally different", confidence=0.9)
    existing = [_record("mem_b", "k2", "other text", confidence=0.5)]
    assert detect_contradiction(candidate, existing) == []


def test_detect_contradiction_small_confidence_delta_is_no_op() -> None:
    """Confidence delta below threshold = refinement, not contradiction."""
    candidate = _record("mem_new", "k", "v2 of belief", confidence=0.75)
    existing = [_record("mem_old", "k", "v1 of belief", confidence=0.7)]
    # 0.05 delta < 0.3 default threshold
    assert detect_contradiction(candidate, existing) == []


def test_detect_contradiction_is_deterministic() -> None:
    """Same input => same output (stable, no randomness)."""
    candidate = _record("mem_new", "k", "x is true", confidence=0.9)
    existing = [_record("mem_old", "k", "x is false", confidence=0.5)]
    a = detect_contradiction(candidate, existing)
    b = detect_contradiction(candidate, existing)
    assert a == b
    # judgment_id should be stable for the same pair
    assert a[0].judgment_id == b[0].judgment_id
