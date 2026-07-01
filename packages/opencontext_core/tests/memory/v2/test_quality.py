"""Tests for Memory v2 quality scoring (PR-009)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from opencontext_core.memory.v2.quality import QualityScoreV2, score_quality


def _record(
    content: str = "Use Postgres for durable storage because it has ACID guarantees.",
    evidence_refs: list[str] | None = None,
    confidence: float = 0.8,
    created_at: datetime | None = None,
) -> dict:
    refs = ["src/a.py:1", "src/b.py:2"] if evidence_refs is None else evidence_refs
    return {
        "id": "mem_test",
        "kind": "decision",
        "content": content,
        "evidence_refs": refs,
        "source_refs": ["run_1"],
        "confidence": confidence,
        "created_at": created_at or datetime.now(tz=UTC),
        "updated_at": datetime.now(tz=UTC),
    }


def test_score_quality_returns_four_dimensions() -> None:
    """QualityScoreV2 reports clarity, evidence-anchoring, reusability, temporal-validity."""
    s = score_quality(_record())
    assert isinstance(s, QualityScoreV2)
    assert 0.0 <= s.clarity <= 1.0
    assert 0.0 <= s.evidence_anchoring <= 1.0
    assert 0.0 <= s.reusability <= 1.0
    assert 0.0 <= s.temporal_validity <= 1.0
    assert 0.0 <= s.composite <= 1.0


def test_score_quality_more_evidence_higher_anchoring() -> None:
    """More evidence refs => higher evidence_anchoring, monotonic."""
    low = score_quality(_record(evidence_refs=[]))
    mid = score_quality(_record(evidence_refs=["src/a.py:1"]))
    high = score_quality(_record(evidence_refs=["src/a.py:1", "src/b.py:2", "src/c.py:3"]))
    assert low.evidence_anchoring < mid.evidence_anchoring < high.evidence_anchoring


def test_score_quality_recent_record_higher_temporal_validity() -> None:
    """A record created today scores higher on temporal_validity than one from 100 days ago."""
    now = datetime.now(tz=UTC)
    fresh = _record(created_at=now)
    stale = _record(created_at=now - timedelta(days=100))
    fresh_score = score_quality(fresh)
    stale_score = score_quality(stale)
    assert fresh_score.temporal_validity > stale_score.temporal_validity


def test_score_quality_short_garbage_low_clarity() -> None:
    """Tiny/garbage content scores low on clarity."""
    good = score_quality(_record(content="a " * 80))
    bad = score_quality(_record(content="x"))
    assert good.clarity > bad.clarity
    assert bad.clarity < 0.5
