"""BudgetController — per-phase budget gating for the oc-new conductor.

NOTE: This module is responsible for deciding whether a phase may proceed given
the current token ledger. It does not record tokens — that is handled by
_record_phase_budget in the conductor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opencontext_core.agentic.budget import BudgetLedger


@dataclass(frozen=True)
class BudgetDecision:
    """Result of a budget gate evaluation."""

    allowed: bool
    reason: str
    available_for_phase: int
    should_compress: bool = False
    should_ask_user: bool = False


class BudgetController:
    """Evaluates per-phase token budget decisions from a BudgetLedger."""

    def decide(
        self,
        config: object,
        ledger: object,
        phase: str,
    ) -> BudgetDecision:
        """Return a BudgetDecision for the given phase.

        Parameters
        ----------
        config:
            An AgenticFlowConfig (duck-typed to avoid circular import).
        ledger:
            A BudgetLedger (duck-typed to avoid circular import).
        phase:
            The phase name being evaluated.
        """
        from opencontext_core.agentic.config import BudgetMode

        budget_mode_value = getattr(getattr(config, "budget_mode", None), "value", None)
        if budget_mode_value is None:
            budget_mode_value = str(getattr(config, "budget_mode", "off"))

        total_budget: int | None = getattr(config, "total_budget", None)
        phase_budget: int | None = getattr(config, "phase_budget", None)
        used_total: int = getattr(ledger, "used_total", 0)

        remaining_total = (total_budget - used_total) if total_budget is not None else None
        available = phase_budget if phase_budget is not None else (remaining_total or 0)

        # OFF — no gating at all.
        if budget_mode_value == BudgetMode.OFF:
            return BudgetDecision(
                allowed=True,
                reason="budget_mode=off",
                available_for_phase=available,
            )

        # STRICT — block when budget is exhausted.
        if budget_mode_value == BudgetMode.STRICT:
            if remaining_total is not None and remaining_total <= 0:
                return BudgetDecision(
                    allowed=False,
                    reason=f"strict budget exhausted: used {used_total} / {total_budget}",
                    available_for_phase=0,
                )
            return BudgetDecision(
                allowed=True,
                reason="strict budget within limits",
                available_for_phase=available,
            )

        # ADAPTIVE — allow but request compression.
        if budget_mode_value == BudgetMode.ADAPTIVE:
            return BudgetDecision(
                allowed=True,
                reason="adaptive mode: compression requested",
                available_for_phase=available,
                should_compress=True,
            )

        # ASK — allow but flag for user confirmation.
        if budget_mode_value == BudgetMode.ASK:
            return BudgetDecision(
                allowed=True,
                reason="ask mode: user confirmation requested",
                available_for_phase=available,
                should_ask_user=True,
            )

        # WARN (default) — allow with a warning, no block.
        return BudgetDecision(
            allowed=True,
            reason=f"warn mode: {used_total} tokens used",
            available_for_phase=available,
        )

    def record(
        self,
        ledger: BudgetLedger,
        phase: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        compression_savings: int = 0,
        estimated_cost_usd: float | None = None,
    ) -> BudgetLedger:
        """Append a PhaseBudget entry and return the updated ledger."""
        from opencontext_core.agentic.budget import PhaseBudget

        entry = PhaseBudget(
            phase=phase,
            used_input_tokens=input_tokens,
            used_output_tokens=output_tokens,
            compression_savings=compression_savings,
            estimated_cost_usd=estimated_cost_usd,
        )
        return ledger.add_phase(entry)


if __name__ == "__main__":
    from opencontext_core.agentic.budget import BudgetLedger, PhaseBudget
    from opencontext_core.agentic.config import AgenticFlowConfig, BudgetMode

    controller = BudgetController()

    # OFF — always allowed
    cfg_off = AgenticFlowConfig(budget_mode=BudgetMode.OFF)
    ledger = BudgetLedger(mode="off")
    d = controller.decide(cfg_off, ledger, "explore")
    assert d.allowed

    # STRICT — exhausted budget blocks
    cfg_strict = AgenticFlowConfig(budget_mode=BudgetMode.STRICT, total_budget=100)
    spent_ledger = BudgetLedger(mode="strict", total_budget=100).add_phase(
        PhaseBudget(phase="explore", used_input_tokens=100)
    )
    d_block = controller.decide(cfg_strict, spent_ledger, "apply")
    assert not d_block.allowed, f"Expected blocked, got {d_block}"

    # ADAPTIVE — compress
    cfg_adaptive = AgenticFlowConfig(budget_mode=BudgetMode.ADAPTIVE)
    d_adapt = controller.decide(cfg_adaptive, ledger, "explore")
    assert d_adapt.should_compress

    # ASK — ask user
    cfg_ask = AgenticFlowConfig(budget_mode=BudgetMode.ASK)
    d_ask = controller.decide(cfg_ask, ledger, "explore")
    assert d_ask.should_ask_user

    print("agentic/budget_controller.py self-check passed.")
