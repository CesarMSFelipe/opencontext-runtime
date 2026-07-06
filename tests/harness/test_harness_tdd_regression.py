"""TDD-006: the SDD harness run.json tdd block populates the regression half.

The apply-phase ``tests_pass`` gate is GREEN; the verify phase's suite re-run is
the contract's step-7 regression run. When both recorded a real exit code the
derived tdd block carries the regression command + exit code instead of a
hardcoded ``None``.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.models import BudgetMode, GateStatus, PhaseGate
from opencontext_core.harness.phases import VerifyPhase
from opencontext_core.harness.runner import HarnessRunner


def test_tdd_block_derives_regression_from_verify_rerun(tmp_path: Path) -> None:
    """TDD-006: tdd.regression records the verify suite re-run (command, exit_code)."""
    runner = HarnessRunner(root=tmp_path)
    gates = [
        PhaseGate(
            id="tests_pass",
            phase="apply",
            status=GateStatus.PASSED,
            message="green",
            metadata={"command": "python -m pytest -q tests/test_app.py", "exit_code": 0},
        ),
        PhaseGate(
            id="verify_tests_passed",
            phase="verify",
            status=GateStatus.PASSED,
            message="All checks passed",
            metadata={"command": "python -m pytest -q --tb=short tests", "exit_code": 0},
        ),
    ]

    block = runner._tdd_block_from_gates(gates, created_at="2026-01-01T00:00:00+00:00")

    assert block is not None
    assert block["green"]["command"] == "python -m pytest -q tests/test_app.py"
    assert block["green_proven"] is True
    assert block["regression"] is not None
    assert block["regression"]["command"] == "python -m pytest -q --tb=short tests"
    assert block["regression"]["exit_code"] == 0


def test_tdd_block_keeps_verify_rerun_as_green_fallback(tmp_path: Path) -> None:
    """TDD-006: without an apply-phase GREEN the verify re-run stays the green half."""
    runner = HarnessRunner(root=tmp_path)
    gates = [
        PhaseGate(
            id="verify_tests_passed",
            phase="verify",
            status=GateStatus.FAILED,
            message="Tests exited with code 1 (fix-loop reverify)",
            metadata={"command": "python -m pytest -q", "exit_code": 1},
        )
    ]

    block = runner._tdd_block_from_gates(gates, created_at="2026-01-01T00:00:00+00:00")

    assert block is not None
    assert block["green"]["exit_code"] == 1
    assert block["green_proven"] is False
    assert block["regression"] is None


def test_verify_phase_passing_suite_emits_gate_with_evidence(tmp_path: Path) -> None:
    """TDD-006: a passing verify suite run records a PASSED gate with real evidence."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\nminversion = 6.0\n", encoding="utf-8"
    )
    src = tmp_path / "widget.py"
    src.write_text("VALUE = 1\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_widget.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "verify regression evidence")
    state.apply_edits = [{"path": "widget.py", "content": src.read_text()}]
    phase = VerifyPhase(runner.config.phases.get("verify"), BudgetMode.OFF)
    result = phase.run(state)

    report = json.loads(Path(result.artifacts[0].path).read_text(encoding="utf-8"))
    assert report["tests_executed"] is True

    gate = next((g for g in result.gates if g.id == "verify_tests_passed"), None)
    assert gate is not None, "a passing suite run must persist its gate evidence"
    assert gate.status == GateStatus.PASSED
    assert gate.metadata["exit_code"] == 0
    assert gate.metadata["command"]
