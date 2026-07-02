"""TDD — C12: decisions explain subcommand + --root option.

RED gate: decisions_cmd.py has no explain subcommand and no --root on
list/show. All tests fail until decisions_cmd.py is updated.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from opencontext_core.runtime.decisions import RuntimeDecision, DecisionKind


def _make_run_dir(base: Path, run_id: str, decisions: list[dict]) -> Path:
    """Write a minimal decisions.json for a run and return the run directory."""
    run_dir = base / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "decisions.json").write_text(
        json.dumps({"decisions": decisions}), encoding="utf-8"
    )
    (run_dir / "state.json").write_text("{}", encoding="utf-8")
    return run_dir


def _make_session(root: Path, session_id: str, run_id: str, decisions: list[dict]) -> Path:
    """Create a session directory with one run and return the run directory."""
    storage = root / ".opencontext"
    session_dir = storage / "sessions" / session_id
    return _make_run_dir(session_dir, run_id, decisions)


def _run_decisions(args_list: list[str]) -> int:
    """Invoke decisions CLI, return exit code."""
    from opencontext_cli.commands.decisions_cmd import add_decisions_parser, handle_decisions

    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command")
    add_decisions_parser(subs)
    args = parser.parse_args(args_list)
    try:
        handle_decisions(args)
    except SystemExit as exc:
        return int(exc.code if exc.code is not None else 0)
    return 0


# ---------------------------------------------------------------------------
# explain subcommand
# ---------------------------------------------------------------------------


def test_decisions_explain_returns_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """decisions explain <run_id> --root exits 0 and emits decision rows."""
    sample_decisions = [
        {
            "kind": "workflow",
            "selected": "standard",
            "governed_by": "policy",
            "rationale": "default",
            "alternatives": ["fast"],
            "confidence": 0.9,
            "inputs": {},
        }
    ]
    _make_session(tmp_path, "sess1", "run1", sample_decisions)

    code = _run_decisions(["decisions", "explain", "run1", "--root", str(tmp_path)])
    assert code == 0

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "workflow" in output or "standard" in output or "run1" in output


def test_decisions_explain_unknown_id_exits_nonzero(tmp_path: Path) -> None:
    """decisions explain <nonexistent_id> exits non-zero with readable message."""
    code = _run_decisions(
        ["decisions", "explain", "nonexistent-run", "--root", str(tmp_path)]
    )
    assert code != 0


def test_decisions_explain_no_traceback_on_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """decisions explain with unknown id produces no traceback."""
    _run_decisions(["decisions", "explain", "nosuch", "--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert "Traceback" not in (captured.out + captured.err)


# ---------------------------------------------------------------------------
# --root scopes the search
# ---------------------------------------------------------------------------


def test_decisions_list_with_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """decisions list --root works and limits scope to the given root."""
    _make_session(tmp_path, "s1", "run_a", [{"kind": "skill", "selected": "x",
                                              "governed_by": "", "rationale": "",
                                              "alternatives": [], "confidence": 1.0,
                                              "inputs": {}}])
    code = _run_decisions(["decisions", "list", "--root", str(tmp_path)])
    assert code == 0


def test_decisions_show_with_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """decisions show <run_id> --root works without error."""
    _make_session(tmp_path, "s1", "run_b", [{"kind": "context", "selected": "y",
                                              "governed_by": "", "rationale": "",
                                              "alternatives": [], "confidence": 1.0,
                                              "inputs": {}}])
    code = _run_decisions(["decisions", "show", "run_b", "--root", str(tmp_path)])
    assert code == 0
