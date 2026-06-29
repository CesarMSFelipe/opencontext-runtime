"""OC Flow token budgets, execution lanes and the budget guard (PR-007, FLOW-10,
FLOW-CONV §6 lanes + profile-aware).

Per-node budgets and the total guard are book doc 04 §19. Lanes (``fast``/``cheap``/
``careful``) are the FLOW-CONV addition: each lane deterministically sets context
depth, diagnosis attempt budget and harness strictness, and maps onto a PR-000.2
execution strategy. Budgets/strictness are also profile-aware — the active execution
profile (PR-000.2) can raise or lower the diagnosis attempt budget.

Cost is estimated deterministically here (PR-011 Runtime Intelligence will replace
the estimates with measured cost — that is a documented seam, not a stub claim).

Layering (doc 58): L9 importing L3 profiles only (downward).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.capabilities.registry import get_profile
from opencontext_core.oc_flow.models import MAX_DIAGNOSIS_ATTEMPTS, Lane

# Per-node token targets (book §19): (soft_min, hard_max). local_inspection is 0 LLM.
OC_FLOW_BUDGETS: dict[str, tuple[int, int]] = {
    "init": (0, 200),
    "gather_context": (2000, 4500),
    "plan": (1000, 2000),
    "mutate": (1500, 3000),
    "local_inspection": (0, 0),
    "diagnose": (2000, 4000),  # per attempt
    "escalation": (0, 1000),
    "consolidation": (0, 1000),
}

# Total guard for a first bugfix (book §19): warn at 7k, fail at 10k.
OC_FLOW_TOTAL_WARN = 7000
OC_FLOW_TOTAL_CEILING = 10000


class LaneConfig(BaseModel):
    """A resolved execution lane (FLOW-CONV §6)."""

    model_config = ConfigDict(extra="forbid")

    lane: Lane
    strategy_id: str = Field(description="PR-000.2 execution strategy this lane maps to.")
    context_depth: int = Field(description="How many context layers to retrieve (higher=deeper).")
    diagnosis_attempts: int = Field(description="Attempt budget the lane permits.")
    harness_strictness: str = Field(description="advisory|warn|strict baseline for the lane.")


# Each lane maps onto a built-in strategy (profiles/strategy.py): fast->performance,
# cheap->low-cost, careful->enterprise. ``careful`` permits more diagnosis attempts
# and a stricter harness than ``fast`` (FLOW-CONV scenario).
_LANES: dict[Lane, LaneConfig] = {
    Lane.FAST: LaneConfig(
        lane=Lane.FAST,
        strategy_id="fast",
        context_depth=2,
        diagnosis_attempts=1,
        harness_strictness="warn",
    ),
    Lane.CHEAP: LaneConfig(
        lane=Lane.CHEAP,
        strategy_id="cheap",
        context_depth=1,
        diagnosis_attempts=1,
        harness_strictness="advisory",
    ),
    Lane.CAREFUL: LaneConfig(
        lane=Lane.CAREFUL,
        strategy_id="careful",
        context_depth=4,
        diagnosis_attempts=MAX_DIAGNOSIS_ATTEMPTS,
        harness_strictness="strict",
    ),
}


def lane_config(lane: Lane | str) -> LaneConfig:
    """Return the resolved configuration for ``lane`` (defaults to ``fast``)."""
    resolved = Lane(str(lane))
    return _LANES[resolved]


def resolve_max_attempts(*, profile: str | None = None, lane: Lane | str | None = None) -> int:
    """Resolve the diagnosis attempt budget (FLOW-6, profile + lane aware).

    Base comes from the active execution profile's ``max_retries`` (balanced=2,
    enterprise=3, low-cost=1); the lane then constrains it — ``careful`` raises it
    toward the ceiling, ``fast``/``cheap`` cap it at one. Never exceeds
    :data:`MAX_DIAGNOSIS_ATTEMPTS`.
    """
    base = 2
    if profile:
        resolved = get_profile(profile)
        if resolved is not None:
            base = resolved.max_retries
    if lane is not None:
        cfg = lane_config(lane)
        if cfg.lane is Lane.CAREFUL:
            base = max(base, cfg.diagnosis_attempts)
        else:
            base = min(base, cfg.diagnosis_attempts)
    return max(1, min(base, MAX_DIAGNOSIS_ATTEMPTS))


class BudgetViolation(BaseModel):
    """A recorded budget overrun (warn or fail)."""

    model_config = ConfigDict(extra="forbid")

    scope: str = Field(description="Node id or 'total'.")
    spent: int
    limit: int
    severity: str = Field(description="'warn' or 'fail'.")


class BudgetGuard:
    """Enforces per-node and total OC Flow token budgets (FLOW-10).

    Records the LLM tokens charged to each node, flags a per-node hard-max overrun
    and the total warn/ceiling breaches. ``violations`` is the audit trail; a
    ``fail`` severity is a guard violation a strict run must surface.
    """

    def __init__(
        self,
        *,
        warn_total: int = OC_FLOW_TOTAL_WARN,
        ceiling_total: int = OC_FLOW_TOTAL_CEILING,
    ) -> None:
        self.warn_total = warn_total
        self.ceiling_total = ceiling_total
        self.per_node: dict[str, int] = {}
        self.violations: list[BudgetViolation] = []

    @property
    def total(self) -> int:
        """Cumulative LLM tokens charged across all nodes."""
        return sum(self.per_node.values())

    def charge(self, node: str, tokens: int) -> list[BudgetViolation]:
        """Charge ``tokens`` to ``node`` and return any new violations it triggers."""
        self.per_node[node] = self.per_node.get(node, 0) + tokens
        new: list[BudgetViolation] = []

        _, hard_max = OC_FLOW_BUDGETS.get(node, (0, OC_FLOW_TOTAL_CEILING))
        if self.per_node[node] > hard_max:
            new.append(
                BudgetViolation(
                    scope=node, spent=self.per_node[node], limit=hard_max, severity="fail"
                )
            )

        total = self.total
        if total > self.ceiling_total:
            new.append(
                BudgetViolation(
                    scope="total", spent=total, limit=self.ceiling_total, severity="fail"
                )
            )
        elif total > self.warn_total:
            new.append(
                BudgetViolation(scope="total", spent=total, limit=self.warn_total, severity="warn")
            )

        self.violations.extend(new)
        return new

    def total_exceeds_ceiling(self) -> bool:
        """True when cumulative tokens breach the hard ceiling (FLOW-10 guard)."""
        return self.total > self.ceiling_total
