"""Runtime intel — what-if cost projection across candidate workflows.

Lives in `runtime/intel/`. Layer L10 (Runtime Intelligence). The
:class:`WhatIfAnalysis` is a thin cost-projection helper that consumes a
list of :class:`Plan` candidates and returns a list of
:class:`CostEstimate` sorted by `cost_usd` ascending. It does NOT mutate
the input plans and never calls an LLM — cost comes from the local
:class:`CostEstimator` (mock rates by default).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from opencontext_core.runtime.intel.simulator import CostEstimator

# ponytail: lanes are a small fixed set; new ones go in design.md.
LANES: tuple[str, ...] = ("default", "deep", "fast", "experimental")


@dataclass
class Plan:
    """Candidate workflow for what-if comparison."""

    workflow: str
    tokens: int
    model: str = "default"
    lane: str = "default"
    duration_s: float = 1.0
    tool_calls: int = 0


@dataclass
class CostEstimate:
    """Projected cost + confidence for a single plan."""

    workflow: str
    lane: str
    input_tokens: int
    output_tokens: int
    tool_calls: int
    duration_s: float
    cost_usd: float
    confidence: float
    assumptions: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class WhatIfAnalysis:
    """Compare ≥3 candidate plans by projected cost, no mutation."""

    def __init__(self, estimator: CostEstimator | None = None) -> None:
        self._estimator = estimator or CostEstimator()

    def compare(self, plans: Iterable[Plan]) -> list[CostEstimate]:
        plans = list(plans)
        if len(plans) < 3:
            raise ValueError(f"WhatIf requires >= 3 plans for ranking; got {len(plans)}")
        estimates = [self._project(p) for p in plans]
        # Sort by cost ascending; do NOT mutate the input list.
        return sorted(estimates, key=lambda e: e.cost_usd)

    def _project(self, plan: Plan) -> CostEstimate:
        # ponytail: split 70/30 input/output as the spec doesn't dictate; explicit assumption
        input_tokens = int(plan.tokens * 0.7)
        output_tokens = plan.tokens - input_tokens
        cost_usd = self._estimator.estimate(plan.tokens, plan.model)
        return CostEstimate(
            workflow=plan.workflow,
            lane=plan.lane,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls=plan.tool_calls,
            duration_s=plan.duration_s,
            cost_usd=cost_usd,
            # ponytail: confidence inversely proportional to cost; cheaper plans more certain
            confidence=_confidence_for(plan),
            assumptions=[
                f"model={plan.model}",
                "token_split=0.7/0.3",
                f"lane={plan.lane}",
            ],
        )


def _confidence_for(plan: Plan) -> float:
    # ponytail: heuristic — small token budgets are more predictable
    if plan.tokens <= 500:
        return 0.9
    if plan.tokens <= 5_000:
        return 0.75
    if plan.tokens <= 20_000:
        return 0.6
    return 0.45
