"""Tests for the `runs` inspection CLI (Workstream J)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from opencontext_cli.commands.run_cmd import handle_run_inspect
from opencontext_cli.contracts.errors import CliContractError


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
    """An unknown run id raises the RUN_NOT_FOUND contract error: the
    dispatcher renders it as a pure JSON envelope under --json and exits 1
    (it used to print bare stderr text with EMPTY stdout — dirty JSON)."""
    with pytest.raises(CliContractError) as exc:
        handle_run_inspect(
            SimpleNamespace(runs_action="show", run_id="ghost", root=str(tmp_path), json=True)
        )
    assert exc.value.code == "RUN_NOT_FOUND"
    assert exc.value.exit_code == 1


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
    """An unknown run id raises the RUN_NOT_FOUND contract error (exit 1 via
    the dispatcher, JSON envelope on stdout under --json)."""
    with pytest.raises(CliContractError) as exc:
        handle_run_inspect(
            SimpleNamespace(runs_action="artifacts", run_id="ghost", root=str(tmp_path), json=True)
        )
    assert exc.value.code == "RUN_NOT_FOUND"
    assert exc.value.exit_code == 1


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


# ---------------------------------------------------------------------------
# OC Flow sessions layout — runs written under
# .opencontext/sessions/<session_id>/runs/<run_id>/ with state.json
# (not run.json) as the primary artifact (OCFlowRunner._persist).
# ---------------------------------------------------------------------------


def _make_oc_flow_run(
    root: Path, session_id: str, run_id: str, *, status: str = "completed"
) -> Path:
    """Write a minimal OC Flow run under sessions/<session_id>/runs/<run_id>/."""
    run_dir = root / ".opencontext" / "sessions" / session_id / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": "opencontext.oc_flow.run_state.v1",
        "run_id": run_id,
        "session_id": session_id,
        "workflow": "oc-flow",
        "task": "fix failing test",
        "lane": "fast",
        "profile": "balanced",
        "status": status,
        "graph_status": "completed",
        "completion_reason": "graph reached terminal node",
        "mutation_required": False,
        "visited": ["start", "gather", "completed"],
        "changed_files": [],
    }
    (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return run_dir


def test_runs_list_finds_oc_flow_sessions_layout(tmp_path, capsys) -> None:
    """runs list must return run IDs written by oc_flow under sessions/*/runs/*.

    Previous implementation only scanned .opencontext/runs/* and missed this path.
    """
    _make_oc_flow_run(tmp_path, "sess-ocf-001", "ocflow-list-001")

    handle_run_inspect(SimpleNamespace(runs_action="list", root=str(tmp_path), json=True))
    ids = json.loads(capsys.readouterr().out)
    assert "ocflow-list-001" in ids, f"Expected ocflow-list-001 in list, got: {ids}"


def test_runs_show_finds_oc_flow_sessions_layout(tmp_path, capsys) -> None:
    """runs show <run_id> must find a run in sessions/<session_id>/runs/<run_id>."""
    _make_oc_flow_run(tmp_path, "sess-ocf-002", "ocflow-show-001")

    handle_run_inspect(
        SimpleNamespace(
            runs_action="show",
            run_id="ocflow-show-001",
            root=str(tmp_path),
            json=True,
            profile=False,
        )
    )

    out = json.loads(capsys.readouterr().out)
    assert out["run_id"] == "ocflow-show-001"
    assert out["workflow"] == "oc-flow"
    assert out["status"] == "completed"


def test_runs_list_finds_both_legacy_and_sessions_layout(tmp_path, capsys) -> None:
    """runs list must include runs from both .opencontext/runs/* AND sessions/*/runs/*."""
    _make_run(tmp_path, "harness-run-001")
    _make_oc_flow_run(tmp_path, "sess-ocf-003", "ocflow-mixed-001")

    handle_run_inspect(SimpleNamespace(runs_action="list", root=str(tmp_path), json=True))
    ids = json.loads(capsys.readouterr().out)
    assert "harness-run-001" in ids, "Legacy harness run missing from list"
    assert "ocflow-mixed-001" in ids, "OC Flow sessions-layout run missing from list"
