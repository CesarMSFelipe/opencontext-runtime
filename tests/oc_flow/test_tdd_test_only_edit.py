"""TDD-POL-SUSPICIOUS: test-only edits are suspicious when a functional change was required.

Policy: if the executor edits ONLY test files to make them pass while the task
required a functional (non-test) change, the run is flagged with the
``TDD_TEST_ONLY_EDIT`` violation and may not report a clean ``completed``/
``passed`` — rewriting the failing test to assert the buggy behavior is gaming,
not a fix.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from opencontext_core.agents.executor import ApplyEdit, ApplyOperation
from opencontext_core.oc_flow.completion import functional_change_expected
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.runner import OCFlowRunner
from opencontext_core.tdd.red_green import (
    TDD_TEST_ONLY_EDIT,
    VIOLATION_REASONS,
    is_test_only_change,
    is_test_path,
)

_TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"

#: An executor that "fixes" the failing test by asserting the buggy behavior.
_GAMED_TEST_EDIT = ApplyEdit(
    path="test_calc.py",
    operation=ApplyOperation.REPLACE_RANGE,
    start_line=4,
    end_line=4,
    content="    assert add(2, 3) == -1",
    reason="make the test pass",
    requirement_refs=["sum"],
)


# ---------------------------------------------------------------------------
# pure helpers — test-path detection and task classification
# ---------------------------------------------------------------------------


def test_is_test_path_matches_test_patterns() -> None:
    """TDD-POL-SUSPICIOUS: test_*.py / *_test.py / tests/** / conftest.py are test paths."""
    assert is_test_path("test_calc.py") is True
    assert is_test_path("tests/test_app.py") is True
    assert is_test_path("pkg/sub/module_test.py") is True
    assert is_test_path("tests/helpers/util.py") is True
    assert is_test_path("tests\\test_win.py") is True
    assert is_test_path("conftest.py") is True
    assert is_test_path("app.py") is False
    assert is_test_path("src/protest.py") is False
    assert is_test_path("attestation/report.py") is False


def test_only_edit_detector_requires_all_files_to_be_tests() -> None:
    """TDD-POL-SUSPICIOUS: the detector fires only when EVERY changed file is a test."""
    assert is_test_only_change(["test_calc.py"]) is True
    assert is_test_only_change(["tests/test_a.py", "tests/conftest.py"]) is True
    assert is_test_only_change(["calc.py", "tests/test_a.py"]) is False
    assert is_test_only_change(["calc.py"]) is False
    assert is_test_only_change([]) is False


def test_functional_change_expected_classifier() -> None:
    """TDD-POL-SUSPICIOUS: fix/implement tasks require a functional change.

    Test-authoring and read-only tasks do not — a test-only edit is their goal.
    """
    assert functional_change_expected("Fix failing test in app.py") is True
    assert functional_change_expected("Implement the parser module") is True
    assert functional_change_expected("Add a unit test for the add function") is False
    assert functional_change_expected("Write tests for the config loader") is False
    assert functional_change_expected("Explain the runtime architecture") is False


# ---------------------------------------------------------------------------
# end-to-end: gaming the failing test must not pass
# ---------------------------------------------------------------------------


def _project(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "test_calc.py").write_text(_TEST, encoding="utf-8")


def test_strict_test_only_rewrite_is_flagged_and_not_passed(tmp_path: Path, monkeypatch) -> None:
    """TDD-POL-SUSPICIOUS: rewriting only the failing test to assert the bug must not pass."""
    monkeypatch.setenv("OPENCONTEXT_TDD_MODE", "strict")
    _project(tmp_path)

    result = OCFlowRunner(root=tmp_path).run(
        "fix failing test",
        lane=Lane.FAST,
        requested_edits=[_GAMED_TEST_EDIT],
        test_command=[sys.executable, "-m", "pytest", "-q", "test_calc.py"],
    )

    assert result.status not in {"completed", "passed"}, (
        "a test-only rewrite satisfied verification but the task required a "
        "functional change — the run must be flagged, not passed"
    )
    assert result.tdd is not None
    assert result.tdd["violation"] == TDD_TEST_ONLY_EDIT
    assert result.exit_code == 6, "TDD strict violations exit 6"
    assert result.completion_reason == VIOLATION_REASONS[TDD_TEST_ONLY_EDIT]
    # The functional bug is still intact — nothing was actually fixed.
    assert (tmp_path / "calc.py").read_text(
        encoding="utf-8"
    ) == "def add(a, b):\n    return a - b\n"

    # The persisted gate catalog records the failed functional-change gate.
    run_dir = result.artifacts_dir.parent.parent
    gates = json.loads((run_dir / "gates.json").read_text(encoding="utf-8"))["gates"]
    gate = next(g for g in gates if g["id"] == "tdd_functional_change_if_required")
    assert gate["status"] == "failed"
    report = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert report["tdd"]["violation"] == TDD_TEST_ONLY_EDIT
    assert report["status"] not in {"completed", "passed"}


def test_strict_functional_fix_is_not_flagged(tmp_path: Path, monkeypatch) -> None:
    """TDD-POL-SUSPICIOUS: a genuine functional fix passes with the gate clean."""
    monkeypatch.setenv("OPENCONTEXT_TDD_MODE", "strict")
    _project(tmp_path)
    fix = ApplyEdit(
        path="calc.py",
        operation=ApplyOperation.REPLACE_RANGE,
        start_line=2,
        end_line=2,
        content="    return a + b",
        reason="fix",
        requirement_refs=["sum"],
    )

    result = OCFlowRunner(root=tmp_path).run(
        "fix failing test",
        lane=Lane.FAST,
        requested_edits=[fix],
        test_command=[sys.executable, "-m", "pytest", "-q", "test_calc.py"],
    )

    assert result.status == "completed"
    assert result.tdd is not None
    assert "violation" not in result.tdd
    run_dir = result.artifacts_dir.parent.parent
    gates = json.loads((run_dir / "gates.json").read_text(encoding="utf-8"))["gates"]
    gate = next(g for g in gates if g["id"] == "tdd_functional_change_if_required")
    assert gate["status"] == "passed"


def test_default_posture_keeps_test_authoring_tasks_unaffected(tmp_path: Path, monkeypatch) -> None:
    """TDD-POL-SUSPICIOUS: outside strict mode a test-only edit is not flagged."""
    monkeypatch.delenv("OPENCONTEXT_TDD_MODE", raising=False)
    _project(tmp_path)

    result = OCFlowRunner(root=tmp_path).run(
        "fix failing test",
        lane=Lane.FAST,
        requested_edits=[_GAMED_TEST_EDIT],
        test_command=[sys.executable, "-m", "pytest", "-q", "test_calc.py"],
    )

    assert result.tdd is not None
    assert result.tdd.get("violation") != TDD_TEST_ONLY_EDIT
