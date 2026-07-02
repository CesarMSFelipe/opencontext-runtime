"""Context v2 ranking.score — L4 usefulness formula (CONV2).

Usefulness = ``0.5 * relevance + 0.3 * freshness + 0.2 * confidence``. The three
weights sum to 1.0 so the score lives in ``[0, 1]`` when inputs are clamped.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UsefulnessWeights:
    relevance: float
    freshness: float
    confidence: float


DEFAULT_WEIGHTS = UsefulnessWeights(relevance=0.5, freshness=0.3, confidence=0.2)
LAYER_WEIGHTS = DEFAULT_WEIGHTS  # NOTE: L4 layer uses the same defaults.


@dataclass
class UsefulnessScore:
    value: float
    breakdown: dict[str, float] = field(default_factory=dict)


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def usefulness(
    *,
    relevance: float,
    freshness: float,
    confidence: float,
    weights: UsefulnessWeights = DEFAULT_WEIGHTS,
) -> float:
    """Compute L4 usefulness: ``w_r*rel + w_f*fresh + w_c*conf`` (clamped)."""
    rel = _clamp01(float(relevance))
    fresh = _clamp01(float(freshness))
    conf = _clamp01(float(confidence))
    score = (
        weights.relevance * rel
        + weights.freshness * fresh
        + weights.confidence * conf
    )
    return _clamp01(score)


__all__ = [
    "DEFAULT_WEIGHTS",
    "LAYER_WEIGHTS",
    "UsefulnessScore",
    "UsefulnessWeights",
    "usefulness",
]