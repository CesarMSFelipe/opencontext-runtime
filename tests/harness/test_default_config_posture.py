"""Pin the apply-phase safety posture of the SHIPPED default config.

Every other harness safety test overrides the config first, so a regression in
the defaults (e.g. the TDD pre-gate wired to a phase where it never runs) stays
invisible. These tests run the zero-config ``HarnessConfig`` exactly as users
get it and assert the real posture: advisory-by-default, but the advisory
signals must actually fire.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.config import HarnessConfig
from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.runner import HarnessRunner


def _apply_run(tmp_path: Path):
    target = tmp_path / "feature.py"
    target.write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()  # exists, but no test matching the task
    runner = HarnessRunner(root=tmp_path, config=HarnessConfig())  # DEFAULT config
    result = runner.run(
        "apply-only",
        "brand-new-feature",
        BudgetMode.WARN,
        apply_edits=[{"path": str(target), "content": "x = 2\n"}],
    )
    return result, target


def test_default_tdd_pre_gate_actually_runs_on_apply(tmp_path: Path) -> None:
    """The TDD pre-gate must be reachable in the default config.

    It used to be declared on ``verify`` where it never executed; this asserts it
    now runs as an apply pre-gate so the red-before-green signal is not dead.
    """
    result, _ = _apply_run(tmp_path)
    tdd = [g for g in result.gates if g.id == "failing_test_exists"]
    assert tdd, "failing_test_exists must run as an apply pre-gate in the default config"


def test_default_tdd_is_advisory_not_blocking(tmp_path: Path) -> None:
    """Default ``tdd_mode='ask'``: missing test warns but does not block the write."""
    result, target = _apply_run(tmp_path)
    tdd = [g for g in result.gates if g.id == "failing_test_exists"]
    assert tdd[0].status == GateStatus.WARNING  # advisory, not FAILED
    assert target.read_text(encoding="utf-8") == "x = 2\n"  # write proceeded


def test_default_approval_is_not_required(tmp_path: Path) -> None:
    """Default ``approval_required_for_writes=False``: gate passes, write proceeds.

    Documents the advisory-by-default stance: a caller wanting hard enforcement
    must opt in via config; the default never silently blocks.
    """
    result, target = _apply_run(tmp_path)
    approval = [g for g in result.gates if g.id == "approval_required_for_writes"]
    assert approval and approval[0].status == GateStatus.PASSED
    assert target.read_text(encoding="utf-8") == "x = 2\n"
