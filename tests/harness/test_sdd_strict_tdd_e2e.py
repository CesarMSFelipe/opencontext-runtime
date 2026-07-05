"""SDD strict-TDD RED→mutate→GREEN closes offline via the test_stub gateway.

Regressions for two verification findings:
- test_stub was wired only into OC Flow, so the SDD harness never mutated offline
  (fell back to the mock gateway). It is now honored by HarnessRunner._resolve_gateway.
- The tests_pass (GREEN) gate read tdd_mode only from harness.yaml workflow_defaults,
  so strict TDD set in opencontext.yaml's harness section left GREEN inactive.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.harness.runner import HarnessRunner

_BUGGY = "def add(a, b):\n    return a - b\n"
_TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
_CONFIG = "version: 1\nprovider: test_stub\nedits_file: edits.json\nharness:\n  tdd_mode: strict\n"


def _edit(content: str) -> str:
    return json.dumps(
        [
            {
                "path": "calc.py",
                "operation": "replace_range",
                "start_line": 2,
                "end_line": 2,
                "content": content,
                "reason": "fix",
                "requirement_refs": ["add returns the sum"],
            }
        ]
    )


def _project(tmp_path: Path, edit_content: str) -> Path:
    (tmp_path / "calc.py").write_text(_BUGGY, encoding="utf-8")
    (tmp_path / "test_calc.py").write_text(_TEST, encoding="utf-8")
    (tmp_path / "edits.json").write_text(_edit(edit_content), encoding="utf-8")
    (tmp_path / "opencontext.yaml").write_text(_CONFIG, encoding="utf-8")
    return tmp_path


def _tests_pass_gate(result):
    return next((g for g in result.gates if g.id == "tests_pass"), None)


def test_strict_tdd_correct_fix_mutates_and_green_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The harness conftest pins OPENCONTEXT_TDD_MODE=off for determinism; this
    # test explicitly exercises strict TDD, so opt back in.
    monkeypatch.setenv("OPENCONTEXT_TDD_MODE", "strict")
    root = _project(tmp_path, "    return a + b")
    result = HarnessRunner(root=root).run("sdd", "fix failing test: add must return the sum")

    # test_stub mutated the file offline...
    assert (root / "calc.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"
    # ...and the GREEN gate ran and PASSED. The gate now sanitizes the subprocess env
    # (drops PYTEST_*/COV_*) and adds the project root to PYTHONPATH, so the nested
    # test run is deterministic even inside the parent pytest suite.
    gate = _tests_pass_gate(result)
    assert gate is not None and gate.status == "passed", gate
    assert "inactive" not in (gate.message or "").lower(), gate.message


def test_strict_tdd_wrong_fix_fails_green_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENCONTEXT_TDD_MODE", "strict")
    root = _project(tmp_path, "    return a * b")  # 2*3=6 != 5
    result = HarnessRunner(root=root).run("sdd", "fix failing test: add must return the sum")

    gate = _tests_pass_gate(result)
    assert gate is not None and gate.status == "failed", gate
