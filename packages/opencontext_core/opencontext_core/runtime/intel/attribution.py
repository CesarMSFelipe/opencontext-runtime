"""Runtime intel — token-savings attribution.

Lives in `runtime/intel/`. Layer L10. The :class:`TokenSavingsAttribution`
decomposes a finished run's token savings across the four sources called
out by the PR-011 spec:

  - ``kg_signature``  (KG node-level signature skipping re-reading)
  - ``semantic_compression`` (context-v2 envelope compression)
  - ``cache_hit`` (cache-v2 leaf)
  - ``local_inspection`` (OC-FLOW local-first code inspection)

It also consumes the optional ``usefulness_score`` from PR-010's
``UsefulnessScore`` to record the *applied* weight of the savings.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

_SAVING_KEYS: tuple[str, ...] = (
    "kg_signature",
    "semantic_compression",
    "cache_hit",
    "local_inspection",
)


@dataclass
class TokenSavings:
    """Decomposed token savings across the four PR-011 axes."""

    kg_signature: int
    semantic_compression: int
    cache_hit: int
    local_inspection: int
    applied_score: float = 0.0
    baseline_tokens: int = 0

    @property
    def total(self) -> int:
        return (
            self.kg_signature + self.semantic_compression + self.cache_hit + self.local_inspection
        )

    @property
    def savings_pct(self) -> float:
        # ponytail: 0% when no baseline; no division by zero, no surprises
        if self.baseline_tokens <= 0:
            return 0.0
        return self.total / self.baseline_tokens


def _coerce_int(value: object) -> int:
    if value is None:
        return 0
    try:
        n = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 0
    return max(0, n)  # type: ignore[no-any-return]


def _coerce_float(value: object) -> float:
    if value is None:
        return 0.0
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    # Clamp to [0, 1] — usefulness_score is bounded
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


class TokenSavingsAttribution:
    """Decompose a run's token savings across the four axes."""

    def decompose(self, run: Mapping[str, object]) -> TokenSavings:
        baseline = _coerce_int(run.get("baseline_tokens"))
        axes: dict[str, int] = {key: _coerce_int(run.get(key)) for key in _SAVING_KEYS}
        return TokenSavings(
            kg_signature=axes["kg_signature"],
            semantic_compression=axes["semantic_compression"],
            cache_hit=axes["cache_hit"],
            local_inspection=axes["local_inspection"],
            applied_score=_coerce_float(run.get("usefulness_score")),
            baseline_tokens=baseline,
        )
