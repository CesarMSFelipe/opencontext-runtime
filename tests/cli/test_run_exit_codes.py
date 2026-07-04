"""`opencontext run` exit codes: genuine failures are nonzero, honest states are 0.

Regression: run always returned exit 0, so CI/scripts could not detect a failed or
gate-blocked run. A failed/blocked run now returns 1; honest degraded outcomes
(needs_executor/needs_provider) stay 0 so provider-free journeys are unaffected.
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


def test_needs_executor_run_exits_zero(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    rc = handle_run_exec(_args(tmp_path, "fix the bug in add", "oc-flow"))
    capsys.readouterr()
    assert rc == 0, "an honest needs_executor run must exit 0"


def test_failed_run_exits_nonzero(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    rc = handle_run_exec(_args(tmp_path, "add a multiply function", "sdd"))
    capsys.readouterr()
    assert rc == 1, "a failed run must exit nonzero so CI can detect it"
