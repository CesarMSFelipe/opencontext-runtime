"""CLI readers resolve execution state global-first with legacy fallback.

In user mode (the default) execution artifacts live under the XDG project
workspace; runs persisted before the migration remain under the in-repo
``.opencontext`` tree. Every read surface (``runs``, ``receipt``,
``decisions``, ``session``, ``knowledge-graph explain-pack``) must see both:
the active (global) location first, the legacy in-repo tree as fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from opencontext_cli.commands.decisions_cmd import handle_decisions
from opencontext_cli.commands.receipt_cmd import handle_receipt
from opencontext_cli.commands.run_cmd import handle_run_inspect
from opencontext_cli.commands.session_cmd import handle_session
from opencontext_core.paths import execution_state


@pytest.fixture()
def user_mode_root(tmp_path: Path, xdg_state_tmp: Path) -> Path:
    """A project root in default user-mode storage with isolated XDG state."""
    root = tmp_path / "project"
    root.mkdir()
    # Sanity: user mode must place execution state OUTSIDE the project root.
    workspace = execution_state.execution_workspace(root)
    assert root.resolve() not in [workspace, *workspace.parents], (
        f"expected XDG workspace, got in-repo path {workspace}"
    )
    return root


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_session_run(base: Path, session_id: str, run_id: str) -> Path:
    """Materialise a minimal oc-flow style run under a sessions tree."""
    run_dir = base / session_id / "runs" / run_id
    _write_json(
        run_dir / "state.json",
        {
            "run_id": run_id,
            "session_id": session_id,
            "workflow": "oc-flow",
            "task": "fix bug",
            "status": "completed",
        },
    )
    return run_dir


# --------------------------------------------------------------------- runs


def test_runs_list_sees_user_mode_session_run(user_mode_root: Path, capsys) -> None:
    _seed_session_run(execution_state.sessions_root(user_mode_root), "sess_u", "run_user")
    handle_run_inspect(SimpleNamespace(runs_action="list", root=str(user_mode_root), json=True))
    ids = json.loads(capsys.readouterr().out)
    assert "run_user" in ids


def test_runs_list_sees_legacy_in_repo_run_in_user_mode(user_mode_root: Path, capsys) -> None:
    _write_json(
        user_mode_root / ".opencontext" / "runs" / "run_legacy" / "run.json",
        {"run_id": "run_legacy", "workflow": "sdd", "status": "completed"},
    )
    handle_run_inspect(SimpleNamespace(runs_action="list", root=str(user_mode_root), json=True))
    ids = json.loads(capsys.readouterr().out)
    assert "run_legacy" in ids


def test_runs_show_finds_user_mode_run(user_mode_root: Path, capsys) -> None:
    _seed_session_run(execution_state.sessions_root(user_mode_root), "sess_u", "run_user")
    handle_run_inspect(
        SimpleNamespace(runs_action="show", root=str(user_mode_root), run_id="run_user", json=True)
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["run_id"] == "run_user"
    assert summary["workflow"] == "oc-flow"


def test_runs_artifacts_finds_user_mode_run(user_mode_root: Path, capsys) -> None:
    run_dir = _seed_session_run(execution_state.sessions_root(user_mode_root), "sess_u", "run_user")
    (run_dir / "artifacts").mkdir()
    (run_dir / "artifacts" / "patch.diff").write_text("diff", encoding="utf-8")
    handle_run_inspect(
        SimpleNamespace(
            runs_action="artifacts", root=str(user_mode_root), run_id="run_user", json=True
        )
    )
    names = json.loads(capsys.readouterr().out)
    assert "artifacts/patch.diff" in names


# ------------------------------------------------------------------ receipt


def test_receipt_list_sees_user_mode_receipts(user_mode_root: Path, capsys) -> None:
    run_dir = _seed_session_run(execution_state.sessions_root(user_mode_root), "sess_u", "run_user")
    _write_json(
        run_dir / "artifacts" / "oc-flow" / "apply-receipts.json",
        {"checkpoint_id": "chk_1", "receipts": []},
    )
    handle_receipt(SimpleNamespace(receipt_action="list", root=str(user_mode_root), json=True))
    payload = json.loads(capsys.readouterr().out)
    assert any(entry.get("receipt_id") == "run_user" for entry in payload)


def test_receipt_list_sees_legacy_in_repo_receipts(user_mode_root: Path, capsys) -> None:
    _write_json(
        user_mode_root
        / ".opencontext"
        / "runs"
        / "run_legacy"
        / "artifacts"
        / "oc-flow"
        / "apply-receipts.json",
        {"checkpoint_id": "chk_2", "receipts": []},
    )
    handle_receipt(SimpleNamespace(receipt_action="list", root=str(user_mode_root), json=True))
    payload = json.loads(capsys.readouterr().out)
    assert any(entry.get("receipt_id") == "run_legacy" for entry in payload)


# ---------------------------------------------------------------- decisions


def test_decisions_list_sees_user_mode_run(user_mode_root: Path, capsys) -> None:
    run_dir = _seed_session_run(execution_state.sessions_root(user_mode_root), "sess_u", "run_user")
    _write_json(
        run_dir / "decisions.json",
        {"decisions": [{"kind": "workflow", "selected": "oc-flow"}]},
    )
    handle_decisions(SimpleNamespace(decisions_action="list", root=str(user_mode_root), json=True))
    rows = json.loads(capsys.readouterr().out)
    assert {"run_id": "run_user", "decisions": 1} in rows


def test_decisions_show_sees_legacy_in_repo_run(user_mode_root: Path, capsys) -> None:
    _write_json(
        user_mode_root
        / ".opencontext"
        / "sessions"
        / "sess_l"
        / "runs"
        / "run_legacy"
        / "decisions.json",
        {"decisions": [{"kind": "workflow", "selected": "sdd"}]},
    )
    handle_decisions(
        SimpleNamespace(
            decisions_action="show", root=str(user_mode_root), run_id="run_legacy", json=True
        )
    )
    rows = json.loads(capsys.readouterr().out)
    assert rows == [{"kind": "workflow", "selected": "sdd"}]


# ------------------------------------------------------------------ session


def test_session_list_sees_user_mode_oc_flow_session(user_mode_root: Path, capsys) -> None:
    _seed_session_run(execution_state.sessions_root(user_mode_root), "sess_u", "run_user")
    handle_session(
        SimpleNamespace(session_command="list", root=str(user_mode_root), json=True, output=None)
    )
    sessions = json.loads(capsys.readouterr().out)["sessions"]
    assert any(row["session_id"] == "sess_u" for row in sessions)


def test_session_list_sees_legacy_in_repo_session(user_mode_root: Path, capsys) -> None:
    _write_json(
        user_mode_root / ".opencontext" / "sessions" / "sess_l" / "runs" / "run_l" / "state.json",
        {"run_id": "run_l", "session_id": "sess_l", "workflow": "oc-flow", "status": "completed"},
    )
    handle_session(
        SimpleNamespace(session_command="list", root=str(user_mode_root), json=True, output=None)
    )
    sessions = json.loads(capsys.readouterr().out)["sessions"]
    assert any(row["session_id"] == "sess_l" for row in sessions)


def test_session_status_falls_back_to_legacy_tree(user_mode_root: Path, capsys) -> None:
    _write_json(
        user_mode_root / ".opencontext" / "sessions" / "sess_l" / "runs" / "run_l" / "state.json",
        {"run_id": "run_l", "session_id": "sess_l", "workflow": "oc-flow", "status": "completed"},
    )
    handle_session(
        SimpleNamespace(
            session_command="status",
            session_id="sess_l",
            root=str(user_mode_root),
            json=True,
            output=None,
        )
    )
    data = json.loads(capsys.readouterr().out)
    assert data["session_id"] == "sess_l"
    assert data["active_run_id"] == "run_l"


# --------------------------------------------------------------- explain-pack


def test_kg_explain_pack_finds_user_mode_pack(user_mode_root: Path, capsys) -> None:
    from opencontext_cli.commands.kg_cmd import _handle_explain_pack

    run_dir = _seed_session_run(execution_state.sessions_root(user_mode_root), "sess_u", "run_user")
    _write_json(
        run_dir / "context-pack.json",
        {
            "included": [],
            "omitted": [],
            "used_tokens": 0,
            "available_tokens": 100,
            "omissions": [],
            "context": {"budget_tokens": 100, "kg_nodes_used": 0, "memory_hits": 0},
        },
    )
    _handle_explain_pack(SimpleNamespace(run="run_user", root=str(user_mode_root), json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "run_user"
