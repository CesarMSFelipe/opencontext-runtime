"""TUI screens resolve execution state global-first with legacy fallback.

The runs / run-detail / TDD-gates screens read persisted run bundles; the SDD
screen reads the SDD context file. In user mode (default) that state lives in
the XDG project workspace, while pre-migration artifacts remain under the
in-repo ``.opencontext`` tree — the screens must see both. The uninstall
preview reuses ``verify_no_traces``: workspace scope must never flag XDG
global state as residue (covered in test_uninstall_global_state.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.paths import execution_state


@pytest.fixture()
def user_mode_root(tmp_path: Path, xdg_state_tmp: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    workspace = execution_state.execution_workspace(root)
    assert root.resolve() not in [workspace, *workspace.parents]
    return root


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_run(base: Path, session_id: str, run_id: str, *, tdd: dict | None = None) -> Path:
    run_dir = base / session_id / "runs" / run_id
    payload = {
        "run_id": run_id,
        "session_id": session_id,
        "workflow": "oc-flow",
        "task": "fix bug",
        "status": "completed",
        "created_at": "2026-07-06T00:00:00+00:00",
    }
    if tdd is not None:
        payload["tdd"] = tdd
    _write_json(run_dir / "run.json", payload)
    return run_dir


def test_runs_screen_lists_user_mode_and_legacy_runs(user_mode_root: Path) -> None:
    from opencontext_cli.tui.screens.runs import list_run_rows

    _seed_run(execution_state.sessions_root(user_mode_root), "sess_u", "run_user")
    _write_json(
        user_mode_root / ".opencontext" / "runs" / "run_legacy" / "run.json",
        {"run_id": "run_legacy", "workflow": "sdd", "status": "completed"},
    )
    run_ids = {row["run_id"] for row in list_run_rows(user_mode_root)}
    assert {"run_user", "run_legacy"} <= run_ids


def test_tdd_gates_screen_sees_user_mode_run(user_mode_root: Path) -> None:
    from opencontext_cli.tui.screens.tdd_gates import latest_tdd_rows

    _seed_run(
        execution_state.sessions_root(user_mode_root),
        "sess_u",
        "run_user",
        tdd={"mode": "strict", "red_proven": True, "green_proven": True},
    )
    rows = latest_tdd_rows(user_mode_root)
    assert [row["run_id"] for row in rows] == ["run_user"]
    assert rows[0]["tdd"]["mode"] == "strict"


def test_sdd_screen_reads_active_context_first(user_mode_root: Path) -> None:
    from opencontext_cli.tui.screens.sdd import read_sdd_context

    active = execution_state.execution_workspace(user_mode_root) / "sdd" / "context.json"
    _write_json(active, {"stack": ["python"], "source": "active"})
    _write_json(
        user_mode_root / ".opencontext" / "sdd" / "context.json",
        {"stack": ["python"], "source": "legacy"},
    )
    assert read_sdd_context(user_mode_root)["source"] == "active"


def test_sdd_screen_falls_back_to_legacy_context(user_mode_root: Path) -> None:
    from opencontext_cli.tui.screens.sdd import read_sdd_context

    _write_json(
        user_mode_root / ".opencontext" / "sdd" / "context.json",
        {"stack": ["python"], "source": "legacy"},
    )
    assert read_sdd_context(user_mode_root)["source"] == "legacy"
