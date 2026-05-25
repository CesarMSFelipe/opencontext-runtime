"""Token budget enforcement for SDD phases."""

from __future__ import annotations

from opencontext_core.harness.models import BudgetMode, GateStatus, PhaseLedger


class TokenBudgetEnforcer:
    """Evaluates token usage against per-phase budgets."""

    def evaluate(
        self,
        phase: str,
        used_tokens: int,
        budget_tokens: int,
        mode: BudgetMode = BudgetMode.WARN,
    ) -> PhaseLedger:
        """Evaluate token usage for a phase against its budget.

        Returns a PhaseLedger with status based on the mode:

        - OFF: always PASSED
        - WARN: PASSED if within budget, WARNING if exceeded
        - STRICT: PASSED if within budget, FAILED if exceeded
        """
        if mode is BudgetMode.OFF:
            return PhaseLedger(
                phase=phase,
                used_tokens=used_tokens,
                budget_tokens=budget_tokens,
                budget_mode=mode,
                status=GateStatus.PASSED,
                message="Token budget enforcement disabled.",
            )

        if used_tokens <= budget_tokens:
            return PhaseLedger(
                phase=phase,
                used_tokens=used_tokens,
                budget_tokens=budget_tokens,
                budget_mode=mode,
                status=GateStatus.PASSED,
                message=f"Within token budget ({used_tokens}/{budget_tokens}).",
            )

        status = GateStatus.WARNING if mode is BudgetMode.WARN else GateStatus.FAILED
        return PhaseLedger(
            phase=phase,
            used_tokens=used_tokens,
            budget_tokens=budget_tokens,
            budget_mode=mode,
            status=status,
            message=f"Token budget exceeded: {used_tokens}/{budget_tokens}.",
        )
