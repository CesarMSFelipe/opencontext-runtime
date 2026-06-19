"""Tests for TokenBudgetEnforcer."""

from __future__ import annotations

from opencontext_core.harness.budget import TokenBudgetEnforcer
from opencontext_core.harness.models import BudgetMode, GateStatus


class TestTokenBudgetEnforcer:
    def setup_method(self) -> None:
        self.enforcer = TokenBudgetEnforcer()

    def test_off_mode_always_passes(self) -> None:
        ledger = self.enforcer.evaluate("explore", 999999, 6000, BudgetMode.OFF)
        assert ledger.status == GateStatus.PASSED
        assert "disabled" in ledger.message.lower()

    def test_warn_within_budget(self) -> None:
        ledger = self.enforcer.evaluate("explore", 3000, 6000, BudgetMode.WARN)
        assert ledger.status == GateStatus.PASSED

    def test_warn_exceeded(self) -> None:
        ledger = self.enforcer.evaluate("explore", 7000, 6000, BudgetMode.WARN)
        assert ledger.status == GateStatus.WARNING
        assert "exceeded" in ledger.message.lower()

    def test_strict_within_budget(self) -> None:
        ledger = self.enforcer.evaluate("explore", 5000, 6000, BudgetMode.STRICT)
        assert ledger.status == GateStatus.PASSED

    def test_strict_exceeded(self) -> None:
        ledger = self.enforcer.evaluate("explore", 7000, 6000, BudgetMode.STRICT)
        assert ledger.status == GateStatus.FAILED
        assert "exceeded" in ledger.message.lower()

    def test_at_exact_budget(self) -> None:
        ledger = self.enforcer.evaluate("apply", 12000, 12000, BudgetMode.STRICT)
        assert ledger.status == GateStatus.PASSED

    def test_edge_zero_tokens(self) -> None:
        ledger = self.enforcer.evaluate("review", 0, 4000, BudgetMode.STRICT)
        assert ledger.status == GateStatus.PASSED
        assert ledger.remaining == 4000

    def test_edge_zero_budget(self) -> None:
        ledger = self.enforcer.evaluate("explore", 100, 0, BudgetMode.STRICT)
        assert ledger.status == GateStatus.FAILED

    def test_default_mode_is_warn(self) -> None:
        ledger = self.enforcer.evaluate("explore", 10000, 6000)
        assert ledger.budget_mode == BudgetMode.WARN
        assert ledger.status == GateStatus.WARNING


class TestPhaseLedgerComputesStatus:
    def test_phase_token_ledger_routes_through_enforcer(self) -> None:
        """H5: phases built PhaseLedger directly, leaving status PASSED so the
        budget gate was a no-op. The base helper must compute real status."""
        from opencontext_core.harness.config import PhaseConfig
        from opencontext_core.harness.phases import HarnessPhase

        phase = HarnessPhase(PhaseConfig(budget_tokens=100), BudgetMode.WARN)
        assert phase._token_ledger("explore", 50).status == GateStatus.PASSED
        assert phase._token_ledger("explore", 500).status == GateStatus.WARNING
