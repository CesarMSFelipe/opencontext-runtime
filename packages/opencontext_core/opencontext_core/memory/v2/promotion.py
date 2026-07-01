"""Gated promotion for Memory v2 (PR-009).

Two-threshold policy: below ``keep_threshold`` is REJECT, between thresholds
is KEEP (stored as a soft belief, not promoted into the durable set), above
``promote_threshold`` is PROMOTE. Defaults 60/80 match the spec.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum
from opencontext_core.memory.v2.quality import QualityScoreV2


class PromotionVerdictV2(StrEnum):
    """Three-way gate outcome."""

    REJECT = "reject"
    KEEP = "keep"
    PROMOTE = "promote"


class PromotionPolicyV2(BaseModel):
    """Two-threshold promotion policy (PR-009 §REQ-mem-v2-promotion)."""

    model_config = ConfigDict(extra="forbid")

    keep_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Composite >= this => KEEP."
    )
    promote_threshold: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Composite >= this => PROMOTE."
    )

    def model_post_init(self, _ctx: Any) -> None:
        if self.promote_threshold < self.keep_threshold:
            raise ValueError(
                f"promote_threshold ({self.promote_threshold}) must be >= "
                f"keep_threshold ({self.keep_threshold})"
            )


def _composite_of(score: float | QualityScoreV2 | Any) -> float:
    if isinstance(score, QualityScoreV2):
        return score.composite
    return float(score)


def evaluate_promotion(
    score: float | QualityScoreV2 | Any,
    policy: PromotionPolicyV2,
) -> PromotionVerdictV2:
    """Map a quality score to a REJECT / KEEP / PROMOTE verdict."""
    composite = _composite_of(score)
    if composite >= policy.promote_threshold:
        return PromotionVerdictV2.PROMOTE
    if composite >= policy.keep_threshold:
        return PromotionVerdictV2.KEEP
    return PromotionVerdictV2.REJECT


__all__ = ["PromotionPolicyV2", "PromotionVerdictV2", "evaluate_promotion"]
