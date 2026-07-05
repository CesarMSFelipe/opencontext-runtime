"""Promotion gate (PR-000.4 / SPEC DL-003 / DL-009).

Acceptance: a LearningCandidate is promotable only when ``quality_score >= 80``
AND the supplied evidence carries a ``benchmark_id`` key. Either gate failing
raises the typed rejection; the promoted result exposes the destination record.
"""

from __future__ import annotations

import pytest

from opencontext_core.learning.v2.promotion_gate import (
    MemoryPromotionRejected,
    PromotionGate,
    PromotionResult,
)


def _candidate(quality: int = 90, candidate_id: str = "cand-1") -> object:
    """Trivial stand-in carrying only the fields the gate reads."""

    class _Stub:
        pass

    s = _Stub()
    s.candidate_id = candidate_id
    s.quality_score = quality
    return s


class TestPromotionGateQuality:
    def test_quality_below_80_rejected(self):
        gate = PromotionGate()
        with pytest.raises(MemoryPromotionRejected) as exc:
            gate.promote(_candidate(quality=72), evidence={"benchmark_id": "first_run_v1"})
        assert "quality_below_threshold" in str(exc.value)

    def test_quality_at_80_promoted(self):
        gate = PromotionGate()
        result = gate.promote(_candidate(quality=80), evidence={"benchmark_id": "first_run_v1"})
        assert isinstance(result, PromotionResult)
        assert result.promoted is True
        assert result.benchmark_id == "first_run_v1"

    def test_quality_above_80_with_benchmark_promoted(self):
        gate = PromotionGate()
        result = gate.promote(_candidate(quality=85), evidence={"benchmark_id": "first_run_v1"})
        assert result.promoted is True


class TestPromotionGateBenchmarkEvidence:
    def test_high_quality_without_benchmark_id_rejected(self):
        gate = PromotionGate()
        with pytest.raises(MemoryPromotionRejected) as exc:
            gate.promote(_candidate(quality=95), evidence={"notes": "looks good"})
        assert "benchmark_id" in str(exc.value)

    def test_high_quality_with_empty_evidence_rejected(self):
        gate = PromotionGate()
        with pytest.raises(MemoryPromotionRejected):
            gate.promote(_candidate(quality=95), evidence={})

    def test_benchmark_id_required_field(self):
        """Whether the benchmark_id is ``""`` or ``None``, the gate rejects."""
        gate = PromotionGate()
        with pytest.raises(MemoryPromotionRejected):
            gate.promote(_candidate(quality=90), evidence={"benchmark_id": ""})


class TestPromotionGateResult:
    def test_result_carries_candidate_id_and_destination(self):
        gate = PromotionGate(destination="memory_harness")
        result = gate.promote(
            _candidate(quality=85, candidate_id="cand-42"),
            evidence={"benchmark_id": "first_run_v1"},
        )
        assert result.candidate_id == "cand-42"
        assert result.destination == "memory_harness"
        assert result.quality_score == 85
