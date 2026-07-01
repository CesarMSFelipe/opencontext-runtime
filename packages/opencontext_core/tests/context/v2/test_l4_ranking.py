"""Tests for context.v2.ranking.score — L4 usefulness formula (CONV2)."""

from __future__ import annotations

from opencontext_core.context.v2.ranking.score import (
    DEFAULT_WEIGHTS,
    LAYER_WEIGHTS,
    UsefulnessScore,
    usefulness,
)


def test_weight_sum_equals_one() -> None:
    for weights in (DEFAULT_WEIGHTS, LAYER_WEIGHTS):
        total = weights.relevance + weights.freshness + weights.confidence
        assert abs(total - 1.0) < 1e-9, f"weights sum to {total}, expected 1.0"


def test_usefulness_formula_basic() -> None:
    # UsefulnessScore = 0.5*rel + 0.3*fresh + 0.2*conf
    score = usefulness(relevance=0.8, freshness=0.6, confidence=1.0)
    expected = 0.5 * 0.8 + 0.3 * 0.6 + 0.2 * 1.0
    assert abs(score - expected) < 1e-9


def test_usefulness_clamped_to_unit_interval() -> None:
    # high inputs → still ≤ 1.0 (weights already sum to 1.0)
    score = usefulness(relevance=1.0, freshness=1.0, confidence=1.0)
    assert 0.0 <= score <= 1.0
    assert abs(score - 1.0) < 1e-9


def test_usefulness_score_dataclass_shape() -> None:
    s = UsefulnessScore(
        value=0.5,
        breakdown={"relevance": 0.5, "freshness": 0.5, "confidence": 0.5},
    )
    assert s.value == 0.5
    assert set(s.breakdown) == {"relevance", "freshness", "confidence"}