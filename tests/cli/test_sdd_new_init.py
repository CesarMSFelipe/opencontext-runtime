"""`opencontext sdd new` / `sdd init` must do real filesystem work.

Regression for a validation finding: both verbs routed through the status
resolver and created NOTHING while reporting `blocked` / `next_recommended: init`.
They now create the openspec scaffold they promise.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _args(**kw):
    base = dict(cwd=".", change=None, topic=None, task=None, verbose=False)
    base.update(kw)
    return SimpleNamespace(**base)


def test_sdd_new_creates_change_folder_with_proposal(tmp_path: Path, capsys) -> None:
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    handle_sdd(_args(sdd_command="new", change="add-multiply", cwd=str(tmp_path)))
    change_dir = tmp_path / "openspec" / "changes" / "add-multiply"
    # proposal.md is the canonical artifact name (the status resolver reads it).
    assert (change_dir / "proposal.md").is_file()
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "created"
    assert "proposal.md" in report["artifacts"]


def test_sdd_new_without_name_exits_2(tmp_path: Path) -> None:
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    with pytest.raises(SystemExit) as exc:
        handle_sdd(_args(sdd_command="new", change=None, cwd=str(tmp_path)))
    assert exc.value.code == 2


def test_sdd_init_bootstraps_openspec(tmp_path: Path, capsys) -> None:
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    handle_sdd(_args(sdd_command="init", cwd=str(tmp_path)))
    assert (tmp_path / "openspec" / "changes").is_dir()
    assert (tmp_path / "openspec" / "specs").is_dir()
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "initialized"


def test_sdd_apply_prints_honest_dispatch_note(tmp_path: Path, capsys) -> None:
    """`sdd apply` must not read as 'applied' — it points at the real executor."""
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    handle_sdd(_args(sdd_command="new", change="c1", cwd=str(tmp_path)))
    capsys.readouterr()
    handle_sdd(_args(sdd_command="apply", change="c1", cwd=str(tmp_path)))
    err = capsys.readouterr().err
    assert "run --workflow sdd" in err
