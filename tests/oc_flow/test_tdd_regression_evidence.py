"""TDD-006: RED/GREEN evidence in the report carries a populated regression block.

Contract step 7 ("run the minimal regression suite"): after a proven GREEN on a
strict mutation run, the broader suite is executed once and recorded under the
``run.json`` ``tdd.regression`` block with its real command and exit code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from opencontext_core.agents.executor import ApplyEdit, ApplyOperation
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.runner import OCFlowRunner
from opencontext_core.tdd.red_green import regression_command

_TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
_FIX_EDIT = ApplyEdit(
    path="calc.py",
    operation=ApplyOperation.REPLACE_RANGE,
    start_line=2,
    end_line=2,
    content="    return a + b",
    reason="fix",
    requirement_refs=["sum"],
)


# ---------------------------------------------------------------------------
# regression_command — deriving the broader-suite command
# ---------------------------------------------------------------------------


def test_regression_command_strips_targeted_selection() -> None:
    """TDD-006: the regression command is the runner without targeted test args."""
    cmd = [sys.executable, "-m", "pytest", "-q", "test_calc.py"]
    assert regression_command(cmd) == [sys.executable, "-m", "pytest", "-q"]


def test_regression_command_keeps_suite_wide_command() -> None:
    """TDD-006: a command with no targeted selection is already the suite run."""
    cmd = [sys.executable, "-m", "pytest", "-q"]
    assert regression_command(cmd) == cmd


def test_regression_command_strips_node_id_selections() -> None:
    """TDD-006: pytest node-id selections count as targeted args and are stripped."""
    cmd = ["pytest", "-q", "tests/test_app.py::test_add"]
    assert regression_command(cmd) == ["pytest", "-q"]


# ---------------------------------------------------------------------------
# end-to-end: strict passing run persists tdd.regression
# ---------------------------------------------------------------------------


def test_strict_passing_run_records_regression_evidence(tmp_path: Path, monkeypatch) -> None:
    """TDD-006: run.json tdd.regression is populated on a strict passing run."""
    monkeypatch.setenv("OPENCONTEXT_TDD_MODE", "strict")
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "test_calc.py").write_text(_TEST, encoding="utf-8")

    result = OCFlowRunner(root=tmp_path).run(
        "fix failing test",
        lane=Lane.FAST,
        requested_edits=[_FIX_EDIT],
        test_command=[sys.executable, "-m", "pytest", "-q", "test_calc.py"],
    )

    assert result.status == "completed"
    assert result.tdd is not None
    regression = result.tdd["regression"]
    assert regression is not None, "strict passing run must record regression evidence"
    assert regression["command"], "regression evidence must name its command"
    assert regression["exit_code"] == 0

    # The persisted run.json carries the same populated regression block.
    run_dir = result.artifacts_dir.parent.parent
    report = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert report["tdd"]["regression"]["exit_code"] == 0
    assert report["tdd"]["regression"]["command"]


def test_non_strict_run_does_not_execute_regression_suite(tmp_path: Path, monkeypatch) -> None:
    """TDD-006: the regression re-run is a strict-mode step; default posture skips it."""
    monkeypatch.delenv("OPENCONTEXT_TDD_MODE", raising=False)
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "test_calc.py").write_text(_TEST, encoding="utf-8")

    result = OCFlowRunner(root=tmp_path).run(
        "fix failing test",
        lane=Lane.FAST,
        requested_edits=[_FIX_EDIT],
        test_command=[sys.executable, "-m", "pytest", "-q", "test_calc.py"],
    )

    assert result.status == "completed"
    assert result.tdd is not None
    assert result.tdd["regression"] is None
