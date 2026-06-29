"""SC-013 — RuntimeOptimizationRecommendation model."""

from __future__ import annotations

from opencontext_core.optimization.recommendations import (
    RecommendationTarget,
    RuntimeOptimizationRecommendation,
)


def test_targets_cover_cache_context_profile() -> None:
    assert {t.value for t in RecommendationTarget} == {"cache", "context", "profile"}


def test_recommendation_schema_version_and_fields() -> None:
    rec = RuntimeOptimizationRecommendation(
        target=RecommendationTarget.context,
        title="t",
        rationale="r",
        evidence_ref="telemetry.x",
    )
    assert rec.schema_version == "opencontext.optimization_recommendation.v1"
    assert rec.evidence_ref == "telemetry.x"


def test_recommendation_carries_no_chain_of_thought() -> None:
    # The contract has an evidence ref, never a CoT / reasoning trace field.
    fields = set(RuntimeOptimizationRecommendation.model_fields)
    assert "evidence_ref" in fields
    assert not {"cot", "chain_of_thought", "reasoning", "thoughts"} & fields
