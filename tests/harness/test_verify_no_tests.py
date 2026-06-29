"""PR-004 REQ-12: verify distinguishes "no tests executed" from "all checks passed"."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import VerifyPhase
from opencontext_core.harness.runner import HarnessRunner


def _verify_phase(tmp_path: Path) -> tuple[VerifyPhase, object]:
    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "verify honesty")
    cfg = runner.config.phases.get("verify")
    return VerifyPhase(cfg, BudgetMode.OFF), state


def test_changed_files_with_no_test_is_not_all_checks_passed(tmp_path: Path) -> None:
    phase, state = _verify_phase(tmp_path)
    # A changed source file that maps to no test file (REQ-12 scenario).
    state.apply_edits = [{"path": "src/only_source.py", "content": "x = 1"}]
    result = phase.run(state)

    report = json.loads(Path(result.artifacts[0].path).read_text(encoding="utf-8"))
    assert report["summary"] == "No tests executed for changed files"
    assert report["summary"] != "All checks passed"
    assert report["tests_executed"] is False
    # The verify outcome is a non-PASS advisory, never a silent green.
    assert any(g.id == "verify_no_tests" and g.status == GateStatus.WARNING for g in result.gates)


def test_no_changes_is_not_all_checks_passed(tmp_path: Path) -> None:
    phase, state = _verify_phase(tmp_path)
    state.apply_edits = []
    result = phase.run(state)

    report = json.loads(Path(result.artifacts[0].path).read_text(encoding="utf-8"))
    assert report["tests_executed"] is False
    assert report["summary"] != "All checks passed"
    assert report["summary"] == "No changes to verify"


def test_passing_scoped_test_still_reports_all_checks_passed(tmp_path: Path) -> None:
    # When a real scoped test runs and passes, the honest summary is unchanged.
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\nminversion = 6.0\n", encoding="utf-8"
    )
    src = tmp_path / "widget.py"
    src.write_text("VALUE = 1\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    # Self-contained test (no import of the changed module) so it passes inside the
    # nested pytest subprocess regardless of sys.path — REQ-12 cares about the
    # "tests ran and passed" summary, not the module wiring.
    (tests_dir / "test_widget.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )

    phase, state = _verify_phase(tmp_path)
    state.apply_edits = [{"path": "widget.py", "content": src.read_text()}]
    result = phase.run(state)
    report = json.loads(Path(result.artifacts[0].path).read_text(encoding="utf-8"))
    assert report["tests_executed"] is True
    assert report["summary"] == "All checks passed"
