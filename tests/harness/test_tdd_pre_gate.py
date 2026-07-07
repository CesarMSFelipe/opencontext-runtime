"""TDD failing-test pre-gate tests.

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

    def test_tdd_ask_fails_safe_noninteractive(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("OPENCONTEXT_TDD_MODE", raising=False)
        target = tmp_path / "feature.py"
        target.write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()

        cfg = _apply_config("ask")
        runner = HarnessRunner(root=tmp_path, config=cfg)
        runner.run(
            "apply-only",
            "brand-new-feature",
            BudgetMode.WARN,
            apply_edits=[{"path": str(target), "content": "x = 2\n"}],
        )

        assert target.read_text(encoding="utf-8") == "x = 1\n"

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


class TestBlockedPreGateHonesty:
    """A run blocked before write must stay blocked (TDD_STRICT_CONTRACT).

    Confirmed gap: the ``blocked_pre_gate`` event fired, but the verify
    fix-loop still mutated files and the run reported passed/exit 0, while the
    FAILED ``failing_test_exists`` gate vanished from gates.json — the fix
    loop replaces every ``phase == "verify"`` gate and the pre-gate carried
    phase ``verify``.
    """

    def _blocked_run(self, tmp_path: Path):
        target = tmp_path / "feature.py"
        target.write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_unrelated.py").write_text("def test_x():\n    pass\n")
        runner = HarnessRunner(root=tmp_path, config=_apply_config("strict"))
        result = runner.run(
            "apply-only",
            "brand-new-feature",
            BudgetMode.WARN,
            apply_edits=[{"path": str(target), "content": "x = 2\n"}],
        )
        return runner, result

    def test_blocked_pre_gate_carries_apply_phase(self, tmp_path: Path) -> None:
        """The pre-gate belongs to apply, so verify-gate replacement never drops it."""
        _, result = self._blocked_run(tmp_path)

        tdd_gates = [g for g in result.gates if g.id == "failing_test_exists"]
        assert tdd_gates and tdd_gates[0].status == GateStatus.FAILED
        assert tdd_gates[0].phase == "apply", (
            "failing_test_exists is an apply PRE-gate; phase 'verify' lets the "
            "fix-loop's verify-gate replacement drop it from gates.json"
        )

    def test_blocked_run_persists_gate_and_tdd_violation(self, tmp_path: Path) -> None:
        """gates.json keeps the FAILED gate; run.json records the violation + exit 6."""
        import json

        from opencontext_core.paths.execution_state import runs_root

        _, result = self._blocked_run(tmp_path)

        assert result.status == GateStatus.FAILED
        run_dir = runs_root(tmp_path) / result.run_id
        gates = json.loads((run_dir / "gates.json").read_text(encoding="utf-8"))["gates"]
        persisted = [g for g in gates if g.get("id") == "failing_test_exists"]
        assert persisted and persisted[0]["status"] == "failed", (
            "the FAILED strict pre-gate must persist in gates.json, not only events.json"
        )
        run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        tdd = run_json.get("tdd") or {}
        assert tdd.get("violation"), "a strict run blocked on RED must record a TDD violation"
        assert run_json.get("exit_code") == 6, run_json.get("exit_code")

    def test_fix_loop_never_resurrects_a_blocked_run(self, tmp_path: Path) -> None:
        """apply never wrote — there is nothing legitimate for the fix-loop to fix."""
        from opencontext_core.harness.models import PhaseGate
        from opencontext_core.harness.runner import HarnessState

        cfg = _apply_config("strict")
        cfg.gate_policy = "block"
        runner = HarnessRunner(root=tmp_path, config=cfg)
        state = HarnessState(run_id="r-blocked", root=tmp_path, task="t")
        state.apply_blocked_pre_gate = True
        state.delegate = object()  # a real executor is wired
        state.gates = [
            PhaseGate(
                id="verify_tests_passed",
                phase="verify",
                status=GateStatus.FAILED,
                message="tests failed",
            )
        ]

        def _must_not_reapply(*args, **kwargs):
            raise AssertionError("fix-loop must not re-apply after a blocked apply")

        runner._reapply_with_findings = _must_not_reapply  # type: ignore[method-assign]
        status = runner._run_fix_loops(state, GateStatus.FAILED, [], BudgetMode.WARN)
        assert status == GateStatus.FAILED
