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


def _apply_run(tmp_path: Path, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.delenv("OPENCONTEXT_TDD_MODE", raising=False)
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


def test_default_tdd_pre_gate_actually_runs_on_apply(tmp_path: Path, monkeypatch) -> None:
    """The TDD pre-gate must be reachable in the default config.

    It used to be declared on ``verify`` where it never executed; this asserts it
    now runs as an apply pre-gate so the red-before-green signal is not dead.
    """
    result, _ = _apply_run(tmp_path, monkeypatch)
    tdd = [g for g in result.gates if g.id == "failing_test_exists"]
    assert tdd, "failing_test_exists must run as an apply pre-gate in the default config"


def test_default_tdd_ask_blocks_noninteractive_apply(tmp_path: Path, monkeypatch) -> None:
    """Default ``tdd_mode='ask'`` fails closed in non-interactive harness runs."""
    result, target = _apply_run(tmp_path, monkeypatch)
    tdd = [g for g in result.gates if g.id == "failing_test_exists"]
    assert tdd[0].status == GateStatus.FAILED
    assert "Non-interactive run blocked" in tdd[0].message
    assert target.read_text(encoding="utf-8") == "x = 1\n"


def test_default_approval_is_not_required(tmp_path: Path, monkeypatch) -> None:
    """Default ``approval_required_for_writes=False``: approval gate passes.

    TDD ask may still block non-interactive apply; this assertion only pins
    approval posture.
    """
    result, _target = _apply_run(tmp_path, monkeypatch)
    approval = [g for g in result.gates if g.id == "approval_required_for_writes"]
    assert approval and approval[0].status == GateStatus.PASSED
