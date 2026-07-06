"""EXE-002 (plan doc 1 §14) — ``policies.shell.allow: false`` blocks the real
harness command-execution path.

Executor ``can_run_commands=False`` flags are declaration-only; the only real
command-execution seam is ``VerifyPhase._run_tests`` (the branch that reaches
``subprocess.run``). These tests prove a command is refused on that path when
shell is disallowed — before any subprocess is spawned — and that the default
(no ``policies:`` section) behavior is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import opencontext_core.harness.phases as phases_mod
from opencontext_core.harness.config import PhaseConfig
from opencontext_core.harness.models import BudgetMode
from opencontext_core.harness.phases import VerifyPhase


def _repo_with_scoped_test(tmp_path: Path) -> Path:
    (tmp_path / "widget.py").write_text("VALUE = 1\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_widget.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    return tmp_path


def test_shell_disabled_blocks_real_command_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EXE-002: with ``policies: shell: allow: false`` in opencontext.yaml the
    harness test-runner refuses the command on the real execution path —
    ``subprocess.run`` is never reached."""
    root = _repo_with_scoped_test(tmp_path)
    (root / "opencontext.yaml").write_text(
        "project:\n  name: demo\npolicies:\n  shell:\n    allow: false\n",
        encoding="utf-8",
    )

    def _forbidden_run(*args: object, **kwargs: object) -> object:
        raise AssertionError("subprocess.run must not be reached when shell is disabled")

    monkeypatch.setattr(phases_mod.subprocess, "run", _forbidden_run)

    phase = VerifyPhase(PhaseConfig(), BudgetMode.OFF)
    result = phase._run_tests(root, changed_files=["widget.py"])
    assert result["exit_code"] != 0
    assert result["tests_executed"] is False
    assert "shell_disabled" in result["error_output"]


def test_shell_enabled_by_default_runs_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EXE-002: without a ``policies.shell`` key the harness command path is
    unchanged — the scoped test command still executes (no default flip)."""
    root = _repo_with_scoped_test(tmp_path)
    calls: dict[str, object] = {}

    class _Completed:
        returncode = 0
        stdout = "1 passed"
        stderr = ""

    def _fake_run(args: list[str], **kwargs: object) -> _Completed:
        calls["args"] = args
        return _Completed()

    monkeypatch.setattr(phases_mod.subprocess, "run", _fake_run)

    phase = VerifyPhase(PhaseConfig(), BudgetMode.OFF)
    result = phase._run_tests(root, changed_files=["widget.py"])
    assert calls, "expected the command to execute when shell is not disabled"
    assert result["tests_executed"] is True
    assert result["exit_code"] == 0


def test_shell_allow_true_keeps_commands_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EXE-002: an explicit ``policies: shell: allow: true`` keeps the harness
    command path enabled (the switch works in both directions)."""
    root = _repo_with_scoped_test(tmp_path)
    (root / "opencontext.yaml").write_text(
        "project:\n  name: demo\npolicies:\n  shell:\n    allow: true\n",
        encoding="utf-8",
    )
    calls: dict[str, object] = {}

    class _Completed:
        returncode = 0
        stdout = "1 passed"
        stderr = ""

    def _fake_run(args: list[str], **kwargs: object) -> _Completed:
        calls["args"] = args
        return _Completed()

    monkeypatch.setattr(phases_mod.subprocess, "run", _fake_run)

    phase = VerifyPhase(PhaseConfig(), BudgetMode.OFF)
    result = phase._run_tests(root, changed_files=["widget.py"])
    assert calls
    assert result["tests_executed"] is True
