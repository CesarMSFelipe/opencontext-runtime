"""OC Flow RED-first pre-check fires ONLY under a strict-TDD posture.

Regression/feature: a "fix" task on an already-green test used to report completed
without having fixed anything (verification runs only AFTER mutation). The RED-first
pre-check blocks that — but ONLY under strict TDD, so default ("ask"/"off") flows
are unchanged (a prior universal version broke legit flows).
"""

from __future__ import annotations

import sys
from pathlib import Path

from opencontext_core.agents.executor import ApplyEdit, ApplyOperation
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.runner import OCFlowRunner

_TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
_EDIT = ApplyEdit(
    path="calc.py",
    operation=ApplyOperation.REPLACE_RANGE,
    start_line=2,
    end_line=2,
    content="    return a + b",
    reason="fix",
    requirement_refs=["sum"],
)


def _project(tmp_path: Path, calc: str) -> None:
    (tmp_path / "calc.py").write_text(calc, encoding="utf-8")
    (tmp_path / "test_calc.py").write_text(_TEST, encoding="utf-8")


def _run(tmp_path: Path):
    return OCFlowRunner(root=tmp_path).run(
        "fix failing test",
        lane=Lane.FAST,
        requested_edits=[_EDIT],
        test_command=[sys.executable, "-m", "pytest", "-q", "test_calc.py"],
    )


def test_strict_blocks_mutation_on_already_green_test(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENCONTEXT_TDD_MODE", "strict")
    _project(tmp_path, "def add(a, b):\n    return a + b\n")  # already green
    result = _run(tmp_path)
    assert result.status != "completed", "strict RED-first must not complete on a green test"
    assert (tmp_path / "calc.py").read_text(
        encoding="utf-8"
    ) == "def add(a, b):\n    return a + b\n"


def test_strict_mutates_on_red_test(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENCONTEXT_TDD_MODE", "strict")
    _project(tmp_path, "def add(a, b):\n    return a - b\n")  # red
    result = _run(tmp_path)
    assert result.status == "completed"
    assert (tmp_path / "calc.py").read_text(
        encoding="utf-8"
    ) == "def add(a, b):\n    return a + b\n"


def test_default_posture_unaffected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENCONTEXT_TDD_MODE", raising=False)
    _project(tmp_path, "def add(a, b):\n    return a + b\n")  # green, but ask posture
    result = _run(tmp_path)
    # No RED pre-check under "ask": the flow behaves as before (completes).
    assert result.status == "completed"
