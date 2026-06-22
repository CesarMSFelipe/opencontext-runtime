"""Regression net for the B4 dead-code delete.

Removing the dead ``_packs()`` handler and its signing import MUST NOT touch:
- the deprecated top-level ``packs`` command (still errors + exits 2), or
- the live ``workflows list`` / ``workflows inspect`` path, which depends on the
  shared ``_workflow_pack_names`` / ``_workflow_pack_metadata`` helpers.

These tests pass against the pre-change tree and are the guard that the delete
did not over-reach (B4-REQ-1, B4-REQ-2; Scenarios B4-1a, B4-2a).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import opencontext_cli.main as cli_main


def test_deprecated_packs_command_still_errors_and_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    # ``packs`` is in _DEPRECATED; argparse routes the unknown command through the
    # overridden error() which prints the removal notice and exits 2 (B4-1a).
    monkeypatch.setattr(sys, "argv", ["opencontext", "packs"])
    with pytest.raises(SystemExit) as exc:
        cli_main._build_parser().parse_args(["packs"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "'packs' has been removed." in err


def test_workflows_list_uses_surviving_helper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # Proves _workflow_pack_names() survives and feeds the live ``workflows list``
    # command (B4-2a). Run from a tmp cwd so the result is deterministic.
    packs_root = tmp_path / "workflow-packs"
    (packs_root / "demo-pack").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    cli_main._workflows("list", None)
    out = capsys.readouterr().out
    assert json.loads(out) == ["demo-pack"]


def test_workflows_inspect_uses_surviving_helper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # Proves _workflow_pack_metadata() survives and feeds ``workflows inspect``.
    pack_dir = tmp_path / "workflow-packs" / "demo-pack"
    pack_dir.mkdir(parents=True)
    (pack_dir / "workflow.yaml").write_text("name: demo\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    cli_main._workflows("inspect", "demo-pack")
    meta = json.loads(capsys.readouterr().out)
    assert meta["status"] == "available"
    assert meta["name"] == "demo-pack"
    assert "workflow.yaml" in meta["files"]
