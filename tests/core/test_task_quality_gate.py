"""TaskQualityGate — verify task entries link a file path and a req ref.

A task entry is a dict that must contain at least one ``files`` string
(path-like) and at least one ``requirements`` reference (``REQ-N``).
"""

from __future__ import annotations

from opencontext_core.harness.models import GateStatus
from opencontext_core.sdd.task_gate import TaskQualityGate


def test_task_with_path_and_ref_passes() -> None:
    task = {
        "id": "3.1",
        "files": ["packages/opencontext_core/opencontext_core/openspec/config.py"],
        "requirements": ["REQ-01"],
    }
    result = TaskQualityGate().evaluate(task)
    assert result.status == GateStatus.PASSED
    assert result.errors == []


def test_task_missing_req_ref_fails() -> None:
    task = {
        "id": "3.2",
        "files": ["packages/x/foo.py"],
        "requirements": [],
    }
    result = TaskQualityGate().evaluate(task)
    assert result.status == GateStatus.FAILED
    assert any("REQ" in e or "requirement" in e.lower() for e in result.errors)


def test_task_missing_files_fails() -> None:
    task = {"id": "3.3", "files": [], "requirements": ["REQ-04"]}
    result = TaskQualityGate().evaluate(task)
    assert result.status == GateStatus.FAILED
    assert any("path" in e.lower() or "file" in e.lower() for e in result.errors)


def test_task_with_nested_files_string_passes() -> None:
    """A single ``files`` string also counts as a path."""
    task = {
        "id": "3.4",
        "files": "src/module.py",
        "requirements": ["REQ-05"],
    }
    result = TaskQualityGate().evaluate(task)
    assert result.status == GateStatus.PASSED


def test_task_with_string_requirements_passes() -> None:
    """Acceptable to supply a single requirement as a string."""
    task = {
        "id": "3.5",
        "files": ["src/ok.py"],
        "requirements": "REQ-09",
    }
    result = TaskQualityGate().evaluate(task)
    assert result.status == GateStatus.PASSED