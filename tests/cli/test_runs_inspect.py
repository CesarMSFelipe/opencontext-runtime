"""Tests for the `runs` inspection CLI (Workstream J)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from opencontext_cli.commands.run_cmd import handle_run_inspect


def _make_run(root: Path, run_id: str, *, status: str = "passed") -> Path:
    run_dir = root / ".opencontext" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "workflow": "sdd",
                "task": "fix bug",
                "status": status,
                "created_at": "2026-06-24T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "gates.json").write_text(
        json.dumps({"gates": [{"id": "g1"}, {"id": "g2"}]}), encoding="utf-8"
    )
    (run_dir / "artifacts.json").write_text(
        json.dumps({"artifacts": [{"path": "spec.md"}]}), encoding="utf-8"
    )
    return run_dir


def test_list_empty(tmp_path, capsys) -> None:
    handle_run_inspect(SimpleNamespace(runs_action="list", root=str(tmp_path), json=True))
    assert json.loads(capsys.readouterr().out) == []


def test_list_returns_run_ids(tmp_path, capsys) -> None:
    _make_run(tmp_path, "sdd-aaa")
    _make_run(tmp_path, "sdd-bbb")
    handle_run_inspect(SimpleNamespace(runs_action="list", root=str(tmp_path), json=True))
    assert json.loads(capsys.readouterr().out) == ["sdd-aaa", "sdd-bbb"]


def test_show_summary(tmp_path, capsys) -> None:
    _make_run(tmp_path, "sdd-aaa")
    handle_run_inspect(
        SimpleNamespace(runs_action="show", run_id="sdd-aaa", root=str(tmp_path), json=True)
    )
    out = json.loads(capsys.readouterr().out)
    assert out["run_id"] == "sdd-aaa"
    assert out["workflow"] == "sdd"
    assert out["status"] == "passed"
    assert out["gates"] == 2
    assert out["artifacts"] == 1


def test_show_missing_run_exits(tmp_path) -> None:
    with pytest.raises(SystemExit) as exc:
        handle_run_inspect(
            SimpleNamespace(runs_action="show", run_id="ghost", root=str(tmp_path), json=True)
        )
    assert exc.value.code == 1


def test_artifacts_lists_files(tmp_path, capsys) -> None:
    _make_run(tmp_path, "sdd-aaa")
    handle_run_inspect(
        SimpleNamespace(runs_action="artifacts", run_id="sdd-aaa", root=str(tmp_path), json=True)
    )
    names = json.loads(capsys.readouterr().out)
    assert "run.json" in names
    assert "gates.json" in names
    assert "artifacts.json" in names


def test_artifacts_missing_run_exits(tmp_path) -> None:
    with pytest.raises(SystemExit) as exc:
        handle_run_inspect(
            SimpleNamespace(runs_action="artifacts", run_id="ghost", root=str(tmp_path), json=True)
        )
    assert exc.value.code == 1


def test_list_unions_runstore_index_and_disk(tmp_path, capsys) -> None:
    # A run only in the RunStore index (no run.json on disk) still lists.
    from opencontext_core.harness.run_store import RunStore

    _make_run(tmp_path, "sdd-disk")
    RunStore(tmp_path).register("sdd-indexed", tmp_path / "elsewhere")
    handle_run_inspect(SimpleNamespace(runs_action="list", root=str(tmp_path), json=True))
    ids = json.loads(capsys.readouterr().out)
    assert "sdd-disk" in ids
    assert "sdd-indexed" in ids


def test_unknown_action_exits(tmp_path) -> None:
    with pytest.raises(SystemExit):
        handle_run_inspect(SimpleNamespace(runs_action=None, root=str(tmp_path)))
