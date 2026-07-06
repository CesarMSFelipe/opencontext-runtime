"""`opencontext run` exit codes follow the RUN_STATE_CONTRACT mapping.

A workflow run must exit with the code of its canonical final state so CI can
never mistake a degraded run for success: needs_executor -> 5, failed/blocked
-> 1 (verification failure -> 8), passed -> 0.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from opencontext_cli.commands.run_cmd import handle_run_exec


def _args(tmp_path: Path, task: str, workflow: str) -> SimpleNamespace:
    return SimpleNamespace(
        task=task,
        workflow=workflow,
        lane="fast",
        profile="balanced",
        root=str(tmp_path),
        config=None,
        json=True,
        yes=True,
        non_interactive=True,
        resume=None,
    )


def test_needs_executor_run_exits_five(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    rc = handle_run_exec(_args(tmp_path, "fix the bug in add", "oc-flow"))
    capsys.readouterr()
    assert rc == 5, "a needs_executor workflow run must exit 5 (RUN_STATE_CONTRACT)"


def test_failed_run_exits_nonzero(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    rc = handle_run_exec(_args(tmp_path, "add a multiply function", "sdd"))
    capsys.readouterr()
    assert rc == 1, "a failed run must exit nonzero so CI can detect it"
