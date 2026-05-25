"""Tests for harness models and enums."""

from __future__ import annotations

from opencontext_core.harness.models import (
    BudgetMode,
    GateStatus,
    PhaseLedger,
    PhaseGate,
    HarnessArtifact,
    HarnessDecision,
    HarnessRunResult,
)


class TestBudgetMode:
    def test_values(self) -> None:
        assert BudgetMode.OFF == "off"
        assert BudgetMode.WARN == "warn"
        assert BudgetMode.STRICT == "strict"

    def test_from_string(self) -> None:
        assert BudgetMode("off") is BudgetMode.OFF
        assert BudgetMode("warn") is BudgetMode.WARN
        assert BudgetMode("strict") is BudgetMode.STRICT


class TestGateStatus:
    def test_values(self) -> None:
        assert GateStatus.PASSED == "passed"
        assert GateStatus.WARNING == "warning"
        assert GateStatus.FAILED == "failed"
        assert GateStatus.SKIPPED == "skipped"


class TestPhaseLedger:
    def test_within_budget(self) -> None:
        ledger = PhaseLedger(
            phase="explore",
            used_tokens=3000,
            budget_tokens=6000,
            budget_mode=BudgetMode.WARN,
        )
        assert ledger.status == GateStatus.PASSED
        assert not ledger.exceeded
        assert ledger.remaining == 3000

    def test_exceeded(self) -> None:
        ledger = PhaseLedger(
            phase="apply",
            used_tokens=15000,
            budget_tokens=12000,
            budget_mode=BudgetMode.STRICT,
        )
        assert ledger.exceeded
        assert ledger.remaining == 0

    def test_at_exact_budget(self) -> None:
        ledger = PhaseLedger(
            phase="verify",
            used_tokens=4000,
            budget_tokens=4000,
            budget_mode=BudgetMode.WARN,
        )
        assert not ledger.exceeded
        assert ledger.remaining == 0

    def test_zero_used(self) -> None:
        ledger = PhaseLedger(
            phase="archive",
            used_tokens=0,
            budget_tokens=2000,
            budget_mode=BudgetMode.WARN,
        )
        assert not ledger.exceeded
        assert ledger.remaining == 2000


class TestPhaseGate:
    def test_create(self) -> None:
        g = PhaseGate(
            id="test-gate",
            phase="explore",
            status=GateStatus.PASSED,
            message="All good",
        )
        assert g.id == "test-gate"
        assert g.metadata == {}

    def test_with_metadata(self) -> None:
        g = PhaseGate(
            id="scan",
            phase="verify",
            status=GateStatus.WARNING,
            message="Found issues",
            metadata={"count": 3},
        )
        assert g.metadata["count"] == 3


class TestHarnessArtifact:
    def test_create(self) -> None:
        a = HarnessArtifact(
            id="a1", phase="apply", path="/tmp/out.json", kind="json"
        )
        assert a.kind == "json"
        assert a.description == ""

    def test_with_description(self) -> None:
        a = HarnessArtifact(
            id="a2",
            phase="explore",
            path="/tmp/pack.json",
            kind="context-pack",
            description="Context pack for auth task",
        )
        assert "auth" in a.description


class TestHarnessDecision:
    def test_create(self) -> None:
        d = HarnessDecision(
            id="d1", phase="propose", status="approved", rationale="LGTM"
        )
        assert d.trace_id is None
        assert d.metadata == {}

    def test_with_trace(self) -> None:
        d = HarnessDecision(
            id="d2",
            phase="apply",
            status="rejected",
            rationale="Budget exceeded",
            trace_id="trace-123",
        )
        assert d.trace_id == "trace-123"


class TestHarnessRunResult:
    def test_create(self) -> None:
        r = HarnessRunResult(
            run_id="test-123",
            workflow="sdd",
            task="fix auth",
            status=GateStatus.PASSED,
        )
        assert r.trace_ids == []
        assert r.created_at is not None

    def test_with_ledgers(self) -> None:
        r = HarnessRunResult(
            run_id="test-456",
            workflow="sdd",
            task="refactor",
            status=GateStatus.PASSED,
            ledgers=[
                PhaseLedger(
                    phase="explore",
                    used_tokens=5000,
                    budget_tokens=6000,
                    budget_mode=BudgetMode.WARN,
                )
            ],
        )
        assert len(r.ledgers) == 1
        assert r.ledgers[0].phase == "explore"
