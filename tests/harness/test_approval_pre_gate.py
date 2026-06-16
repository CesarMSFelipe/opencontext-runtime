"""Approval-before-writes pre-gate tests (, tasks 3.2, 3.6).

``ApprovalRequiredForWritesGate`` must:
  - be decoupled from ``budget_mode`` (driven by an ``approval_required`` flag), and
  - be evaluated by the runner BEFORE ApplyPhase touches any file, blocking the
    write when approval is declared but not granted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.harness.config import HarnessConfig, PhaseConfig
from opencontext_core.harness.gates import ApprovalRequiredForWritesGate
from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.runner import HarnessRunner


class TestApprovalGateDecoupled:
    def test_blocks_when_required_and_not_approved_regardless_of_budget(self) -> None:
        gate = ApprovalRequiredForWritesGate()
        # approval_required=True, approved=False -> FAILED, independent of budget_mode.
        result = gate.evaluate(approval_required=True, approved=False)
        assert result.status == GateStatus.FAILED

    def test_passes_when_required_and_approved(self) -> None:
        gate = ApprovalRequiredForWritesGate()
        result = gate.evaluate(approval_required=True, approved=True)
        assert result.status == GateStatus.PASSED

    def test_passes_when_not_required(self) -> None:
        gate = ApprovalRequiredForWritesGate()
        result = gate.evaluate(approval_required=False, approved=False)
        assert result.status == GateStatus.PASSED


def _apply_only_config_with_approval() -> HarnessConfig:
    cfg = HarnessConfig()
    # Declare the approval gate for the apply phase, and require approval.
    cfg.phases["apply"] = PhaseConfig(
        budget_tokens=12000,
        gates=["approval_required_for_writes"],
    )
    cfg.approval_required_for_writes = True
    return cfg


class TestApprovalPreGateBlocksBeforeApply:
    def test_unapproved_write_blocked_before_any_edit(self, tmp_path: Path) -> None:
        target = tmp_path / "guarded.py"
        target.write_text("SAFE = 1\n", encoding="utf-8")

        cfg = _apply_only_config_with_approval()
        runner = HarnessRunner(root=tmp_path, config=cfg)
        # Edits are queued, but approval is NOT granted.
        result = runner.run(
            "apply-only",
            "needs approval",
            BudgetMode.WARN,
            apply_edits=[{"path": str(target), "content": "HACKED = 1\n"}],
            approved_phases=set(),
        )

        # The approval gate failed and appears in the run's gate list.
        approval_gates = [g for g in result.gates if g.id == "approval_required_for_writes"]
        assert approval_gates, "approval gate must be dispatched as a pre-gate"
        assert approval_gates[0].status == GateStatus.FAILED
        # No file was edited.
        assert target.read_text(encoding="utf-8") == "SAFE = 1\n"
        # Run status reflects the blocked write.
        assert result.status == GateStatus.FAILED

    def test_approved_write_proceeds(self, tmp_path: Path) -> None:
        target = tmp_path / "ok.py"
        target.write_text("V = 0\n", encoding="utf-8")

        cfg = _apply_only_config_with_approval()
        runner = HarnessRunner(root=tmp_path, config=cfg)
        result = runner.run(
            "apply-only",
            "approved change",
            BudgetMode.WARN,
            apply_edits=[{"path": str(target), "content": "V = 99\n"}],
            approved_phases={"apply"},
        )

        approval_gates = [g for g in result.gates if g.id == "approval_required_for_writes"]
        assert approval_gates and approval_gates[0].status == GateStatus.PASSED
        # The edit was applied.
        assert target.read_text(encoding="utf-8") == "V = 99\n"


@pytest.mark.parametrize("budget_mode", [BudgetMode.OFF, BudgetMode.WARN])
def test_approval_independent_of_budget_mode(tmp_path: Path, budget_mode: BudgetMode) -> None:
    target = tmp_path / "x.py"
    target.write_text("a = 1\n", encoding="utf-8")
    cfg = _apply_only_config_with_approval()
    runner = HarnessRunner(root=tmp_path, config=cfg)
    result = runner.run(
        "apply-only",
        "no approval",
        budget_mode,
        apply_edits=[{"path": str(target), "content": "a = 2\n"}],
        approved_phases=set(),
    )
    # Even in non-strict budget modes, the declared approval requirement blocks the write.
    assert target.read_text(encoding="utf-8") == "a = 1\n"
    approval_gates = [g for g in result.gates if g.id == "approval_required_for_writes"]
    assert approval_gates and approval_gates[0].status == GateStatus.FAILED
