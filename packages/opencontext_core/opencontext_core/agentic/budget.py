"""Token budget ledger — append-only audit trail for agentic phase token spend.

NOTE: This module is observational only. Token gating is handled by
TokenBudgetEnforcer (unchanged). BudgetLedger records what was spent per phase
so the AgenticReceipt can summarise it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PhaseBudget(BaseModel, extra="forbid"):
    """Token spend record for a single conductor phase."""

    phase: str
    input_budget: int | None = None
    output_budget: int | None = None
    used_input_tokens: int = 0
    used_output_tokens: int = 0
    compression_savings: int = 0
    estimated_cost_usd: float | None = None
    over_budget: bool = False

    @property
    def total_used(self) -> int:
        """Total tokens consumed in this phase."""
        return self.used_input_tokens + self.used_output_tokens


class BudgetLedger(BaseModel, extra="forbid"):
    """Append-only audit log of token spend across all phases in a run."""

    schema_version: str = "opencontext.budget_ledger.v1"
    mode: str
    total_budget: int | None = None
    phases: list[PhaseBudget] = Field(default_factory=list)

    @property
    def used_total(self) -> int:
        """Sum of all tokens used across every recorded phase."""
        return sum(p.total_used for p in self.phases)

    # NOTE: kept as an alias expected by spec §Domain 3.
    @property
    def total_spent(self) -> int:
        """Alias for used_total (spec compatibility)."""
        return self.used_total

    @property
    def over_budget(self) -> bool:
        """True when total_budget is set and used_total exceeds it."""
        if self.total_budget is None:
            return False
        return self.used_total > self.total_budget

    def add_phase(self, phase: PhaseBudget) -> BudgetLedger:
        """Return a new BudgetLedger with *phase* appended (immutable pattern)."""
        return self.model_copy(update={"phases": [*self.phases, phase]})


if __name__ == "__main__":
    ledger = BudgetLedger(mode="strict", total_budget=1000)
    p1 = PhaseBudget(phase="explore", used_input_tokens=300, used_output_tokens=100)
    p2 = PhaseBudget(phase="spec", used_input_tokens=200, used_output_tokens=50)
    ledger = ledger.add_phase(p1).add_phase(p2)
    assert ledger.total_spent == 650
    assert not ledger.over_budget

    over = BudgetLedger(mode="strict", total_budget=500)
    over = over.add_phase(PhaseBudget(phase="apply", used_input_tokens=400, used_output_tokens=250))
    assert over.over_budget

    print("agentic/budget.py self-check passed.")
