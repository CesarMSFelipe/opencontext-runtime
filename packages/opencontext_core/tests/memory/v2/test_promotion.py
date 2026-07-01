"""Tests for Memory v2 gated promotion (PR-009)."""

from __future__ import annotations

from opencontext_core.memory.v2.promotion import (
    PromotionPolicyV2,
    PromotionVerdictV2,
    evaluate_promotion,
)


def test_promotion_policy_defaults() -> None:
    """Default policy has 60/80 thresholds (REJECT below 60, PROMOTE above 80)."""
    p = PromotionPolicyV2()
    assert p.keep_threshold == 0.6
    assert p.promote_threshold == 0.8


def test_REQ_mem_v2_004_quality_gates() -> None:
    """Below keep => REJECT, between keep and promote => KEEP, above promote => PROMOTE."""
    p = PromotionPolicyV2()
    assert evaluate_promotion(0.0, p) is PromotionVerdictV2.REJECT
    assert evaluate_promotion(0.59, p) is PromotionVerdictV2.REJECT
    assert evaluate_promotion(0.6, p) is PromotionVerdictV2.KEEP
    assert evaluate_promotion(0.79, p) is PromotionVerdictV2.KEEP
    assert evaluate_promotion(0.8, p) is PromotionVerdictV2.PROMOTE
    assert evaluate_promotion(1.0, p) is PromotionVerdictV2.PROMOTE


def test_evaluate_promotion_accepts_quality_score_v2() -> None:
    """evaluate_promotion reads .composite from a QualityScoreV2-like object."""
    from opencontext_core.memory.v2.quality import QualityScoreV2

    p = PromotionPolicyV2()
    score = QualityScoreV2(
        clarity=0.9, evidence_anchoring=0.9, reusability=0.9, temporal_validity=0.9
    )
    # composite is the mean of four 0.9 dims = 0.9
    assert evaluate_promotion(score, p) is PromotionVerdictV2.PROMOTE


def test_evaluate_promotion_custom_thresholds() -> None:
    """Custom thresholds override defaults."""
    p = PromotionPolicyV2(keep_threshold=0.4, promote_threshold=0.5)
    assert evaluate_promotion(0.3, p) is PromotionVerdictV2.REJECT
    assert evaluate_promotion(0.45, p) is PromotionVerdictV2.KEEP
    assert evaluate_promotion(0.55, p) is PromotionVerdictV2.PROMOTE
