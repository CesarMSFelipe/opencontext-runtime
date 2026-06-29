"""Runtime optimization recommendations (PR-000.3 / feeds PR-011).

A recommendation is advice only — it carries a target, a rationale, and an
evidence reference (telemetry/benchmark id), never chain-of-thought. The
Runtime Optimizer emits these; the Runtime Brain / State Machine decide whether
to act (recommend-don't-override discipline, like ``learning/token_optimizer``).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RecommendationTarget(StrEnum):
    """What a recommendation proposes to tune."""

    cache = "cache"
    context = "context"
    profile = "profile"


class RuntimeOptimizationRecommendation(BaseModel):
    """A single recommend-only optimization (no config is mutated by emitting it)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.optimization_recommendation.v1"
    target: RecommendationTarget = Field(description="cache / context / profile.")
    title: str = Field(description="Short, actionable title.")
    rationale: str = Field(description="Why this is recommended (evidence-grounded, no CoT).")
    evidence_ref: str = Field(description="Telemetry / benchmark reference, never CoT.")
    expected_effect: str = Field(
        default="", description="Expected effect, e.g. 'reduce tool calls ~30%'."
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
