"""Tests for oc-new --flow flag — spec §Domain 9."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from opencontext_cli.main import main


def _run(argv: list[str], monkeypatch: object, tmp_path: Path) -> tuple[int, str]:
    import io

    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    with (
        patch.object(sys, "argv", ["opencontext", *argv]),
        patch("sys.stdout", new_callable=io.StringIO) as mock_out,
        patch("sys.stderr", new_callable=io.StringIO),
    ):
        try:
            main()
            rc = 0
        except SystemExit as e:
            rc = int(e.code or 0)
    return rc, mock_out.getvalue()


def test_flow_automatic_starts_run(tmp_path, monkeypatch) -> None:
    rc, out = _run(
        ["oc-new", "start", "add health check", "--flow", "automatic"], monkeypatch, tmp_path
    )
    assert rc == 0
    assert "explore" in out


def test_flow_stepwise_yields_request_approval(tmp_path, monkeypatch) -> None:
    """--flow stepwise: conductor pauses at first non-approval phase."""
    rc, out = _run(
        ["oc-new", "start", "stepwise task", "--flow", "stepwise"], monkeypatch, tmp_path
    )
    assert rc == 0
    # stepwise mode pauses before first phase — next_action.kind = request_approval
    assert "request_approval" in out


def test_flow_none_defaults_to_automatic_behavior(tmp_path, monkeypatch) -> None:
    """No --flow flag: runs like automatic (spawn_subagent on first phase)."""
    rc, out = _run(["oc-new", "start", "no flow flag task"], monkeypatch, tmp_path)
    assert rc == 0
    assert "spawn_subagent" in out


def test_invalid_flow_value_rejected(tmp_path, monkeypatch, capsys) -> None:
    """Invalid --flow value must produce a CLI error."""
    monkeypatch.chdir(tmp_path)
    with patch.object(
        sys, "argv", ["opencontext", "oc-new", "start", "task", "--flow", "invalid-mode"]
    ):
        try:
            main()
            exit_code = 0
        except SystemExit as e:
            exit_code = int(e.code or 0)
    # argparse rejects invalid choices with exit code 2
    assert exit_code == 2


def test_flow_hybrid_starts_run(tmp_path, monkeypatch) -> None:
    rc, _ = _run(["oc-new", "start", "hybrid task", "--flow", "hybrid"], monkeypatch, tmp_path)
    assert rc == 0
