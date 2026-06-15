"""TDD failing-test pre-gate tests (, tasks 3.3, 3.7, 3.8).

The failing-test check (``FailingTestExistsGate``) must run as an apply PRE-gate
(red before green), driven by ``harness.tdd_mode`` (ask/strict/off) read from
config — NOT by token ``budget_mode``.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.config import HarnessConfig, PhaseConfig
from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.runner import HarnessRunner


def _apply_config(tdd_mode: str) -> HarnessConfig:
    cfg = HarnessConfig()
    cfg.phases["apply"] = PhaseConfig(
        budget_tokens=12000,
        gates=["failing_test_exists"],
    )
    cfg.tdd_mode = tdd_mode
    return cfg


class TestTddPreGate:
    def test_strict_tdd_blocks_apply_when_no_failing_test(self, tmp_path: Path) -> None:
        target = tmp_path / "feature.py"
        target.write_text("x = 1\n", encoding="utf-8")
        # tests/ exists but has no matching test for the task.
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_unrelated.py").write_text("def test_x():\n    pass\n")

        cfg = _apply_config("strict")
        runner = HarnessRunner(root=tmp_path, config=cfg)
        result = runner.run(
            "apply-only",
            "brand-new-feature",
            BudgetMode.WARN,  # budget is NOT strict; TDD must still gate.
            apply_edits=[{"path": str(target), "content": "x = 2\n"}],
        )

        tdd_gates = [g for g in result.gates if g.id == "failing_test_exists"]
        assert tdd_gates, "failing_test_exists must run as an apply pre-gate"
        assert tdd_gates[0].status == GateStatus.FAILED
        # Apply was blocked: no edit applied.
        assert target.read_text(encoding="utf-8") == "x = 1\n"

    def test_strict_tdd_allows_apply_when_failing_test_exists(self, tmp_path: Path) -> None:
        target = tmp_path / "feature.py"
        target.write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        # A test matching the task name exists (red-before-green satisfied).
        (tmp_path / "tests" / "test_brand_new_feature.py").write_text(
            "def test_brand_new_feature():\n    assert False\n"
        )

        cfg = _apply_config("strict")
        runner = HarnessRunner(root=tmp_path, config=cfg)
        result = runner.run(
            "apply-only",
            "brand-new-feature",
            BudgetMode.WARN,
            apply_edits=[{"path": str(target), "content": "x = 2\n"}],
        )

        tdd_gates = [g for g in result.gates if g.id == "failing_test_exists"]
        assert tdd_gates and tdd_gates[0].status == GateStatus.PASSED
        assert target.read_text(encoding="utf-8") == "x = 2\n"

    def test_tdd_off_does_not_gate_apply(self, tmp_path: Path) -> None:
        target = tmp_path / "feature.py"
        target.write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()  # no matching test

        cfg = _apply_config("off")
        runner = HarnessRunner(root=tmp_path, config=cfg)
        result = runner.run(
            "apply-only",
            "brand-new-feature",
            BudgetMode.WARN,
            apply_edits=[{"path": str(target), "content": "x = 2\n"}],
        )

        # With tdd off, the failing-test pre-gate does not block apply.
        blocking = [
            g
            for g in result.gates
            if g.id == "failing_test_exists" and g.status == GateStatus.FAILED
        ]
        assert not blocking
        assert target.read_text(encoding="utf-8") == "x = 2\n"

    def test_tdd_enforcement_independent_of_budget_mode(self, tmp_path: Path) -> None:
        """budget_mode WARN + tdd strict still blocks (decoupled from budget)."""
        target = tmp_path / "feature.py"
        target.write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()

        cfg = _apply_config("strict")
        runner = HarnessRunner(root=tmp_path, config=cfg)
        result = runner.run(
            "apply-only",
            "no-test-task",
            BudgetMode.WARN,
            apply_edits=[{"path": str(target), "content": "x = 2\n"}],
        )
        tdd_gates = [g for g in result.gates if g.id == "failing_test_exists"]
        assert tdd_gates and tdd_gates[0].status == GateStatus.FAILED
        assert target.read_text(encoding="utf-8") == "x = 1\n"
