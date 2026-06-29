"""PROD-004 / B1: `run` prints an actionable stderr hint on needs_executor/needs_provider.

The hint must name at least one concrete remedy and go to STDERR so that the
``--json`` STDOUT payload stays pure JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import opencontext_core.oc_flow.cli as oc_flow_cli
from opencontext_cli.commands.run_cmd import handle_run_exec


def _args(tmp_path: Path, *, json_out: bool) -> SimpleNamespace:
    return SimpleNamespace(
        task="Fix failing test",
        workflow="auto",
        lane="fast",
        profile="balanced",
        resume=None,
        root=str(tmp_path),
        config=None,
        json=json_out,
    )


def _stub_returning(status: str):
    """A run_oc_flow_cli stub that mimics --json output and returns a summary."""

    def _stub(task: Any, *, as_json: bool = False, **kwargs: Any) -> dict[str, Any]:
        summary = {"status": status, "workflow": "oc-flow", "run_id": "r1"}
        if as_json:
            print(json.dumps(summary))  # STDOUT, like the real runner
        return summary

    return _stub


def test_needs_executor_prints_hint_to_stderr(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(oc_flow_cli, "run_oc_flow_cli", _stub_returning("needs_executor"))

    handle_run_exec(_args(tmp_path, json_out=True))

    captured = capsys.readouterr()
    # STDOUT is pure JSON (no hint leaked into the machine payload).
    payload = json.loads(captured.out)
    assert payload["status"] == "needs_executor"
    # The hint is on STDERR and names at least one concrete remedy.
    assert "Hint:" in captured.err
    assert "ANTHROPIC_API_KEY" in captured.err
    assert "test_stub" in captured.err
    assert "doctor" in captured.err


def test_needs_provider_prints_hint(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(oc_flow_cli, "run_oc_flow_cli", _stub_returning("needs_provider"))

    handle_run_exec(_args(tmp_path, json_out=False))

    captured = capsys.readouterr()
    assert "Hint:" in captured.err
    assert "MCP sampler" in captured.err


def test_completed_run_emits_no_hint(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(oc_flow_cli, "run_oc_flow_cli", _stub_returning("completed"))

    handle_run_exec(_args(tmp_path, json_out=True))

    captured = capsys.readouterr()
    assert "Hint:" not in captured.err
