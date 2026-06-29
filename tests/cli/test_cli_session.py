"""PR-013 SPEC-CLI-013-09: session list/status/resume/archive round-trip."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from opencontext_cli.commands.session_cmd import handle_session
from opencontext_core.runtime.api import RuntimeApi, StartSessionRequest


def _start_session(root: Path) -> str:
    api = RuntimeApi(root=root)
    ref = api.start_session(StartSessionRequest(task="demo task", root=str(root)))
    return ref.session_id


def test_session_list_status_resume_archive(tmp_path: Path, capsys) -> None:
    sid = _start_session(tmp_path)

    # list
    handle_session(
        SimpleNamespace(session_command="list", root=str(tmp_path), json=True, output="json")
    )
    listed = json.loads(capsys.readouterr().out)
    assert any(s["session_id"] == sid for s in listed["sessions"])

    # status
    handle_session(
        SimpleNamespace(
            session_command="status", session_id=sid, root=str(tmp_path), json=True, output="json"
        )
    )
    status = json.loads(capsys.readouterr().out)
    assert status["session_id"] == sid

    # resume
    handle_session(
        SimpleNamespace(
            session_command="resume", session_id=sid, root=str(tmp_path), json=True, output="json"
        )
    )
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["session_id"] == sid

    # archive
    handle_session(
        SimpleNamespace(
            session_command="archive", session_id=sid, root=str(tmp_path), json=True, output="json"
        )
    )
    archived = json.loads(capsys.readouterr().out)
    assert archived["archived"] is True
    assert archived["status"] == "archived"


def test_session_list_empty(tmp_path: Path, capsys) -> None:
    handle_session(
        SimpleNamespace(session_command="list", root=str(tmp_path), json=True, output="json")
    )
    out = json.loads(capsys.readouterr().out)
    assert out["sessions"] == []


def _write_oc_flow_run(root: Path, sid: str, rid: str, **state: object) -> None:
    """Materialise the oc_flow on-disk layout `opencontext run` writes."""
    run_dir = root / ".opencontext" / "sessions" / sid / "runs" / rid
    run_dir.mkdir(parents=True)
    payload = {
        "schema_version": "opencontext.oc_flow.run_state.v1",
        "run_id": rid,
        "session_id": sid,
        "workflow": "oc-flow",
        "task": "Fix failing test",
        "status": "completed",
    }
    payload.update(state)
    (run_dir / "state.json").write_text(json.dumps(payload), encoding="utf-8")


def test_session_list_reads_oc_flow_tree(tmp_path: Path, capsys) -> None:
    """`session list` surfaces sessions written under .opencontext/sessions/."""
    sid, rid = "sess_OCFLOW1", "run_OCFLOW1"
    _write_oc_flow_run(tmp_path, sid, rid, status="needs_executor")

    handle_session(
        SimpleNamespace(session_command="list", root=str(tmp_path), json=True, output="json")
    )
    listed = json.loads(capsys.readouterr().out)
    row = next(s for s in listed["sessions"] if s["session_id"] == sid)
    assert row["status"] == "needs_executor"
    assert row["workflow"] == "oc-flow"
    assert row["active_run_id"] == rid


def test_session_status_reads_oc_flow_tree(tmp_path: Path, capsys) -> None:
    """`session status <id>` falls back to the oc_flow on-disk session tree."""
    sid, rid = "sess_OCFLOW2", "run_OCFLOW2"
    _write_oc_flow_run(tmp_path, sid, rid, status="completed")

    handle_session(
        SimpleNamespace(
            session_command="status", session_id=sid, root=str(tmp_path), json=True, output="json"
        )
    )
    out = json.loads(capsys.readouterr().out)
    assert out["session_id"] == sid
    assert out["status"] == "completed"
    assert out["workflow"] == "oc-flow"


def test_session_list_unions_legacy_and_oc_flow(tmp_path: Path, capsys) -> None:
    """Legacy SessionStore sessions and oc_flow sessions both appear (union)."""
    legacy_sid = _start_session(tmp_path)
    oc_sid, oc_rid = "sess_OCFLOW3", "run_OCFLOW3"
    _write_oc_flow_run(tmp_path, oc_sid, oc_rid)

    handle_session(
        SimpleNamespace(session_command="list", root=str(tmp_path), json=True, output="json")
    )
    listed = json.loads(capsys.readouterr().out)
    ids = {s["session_id"] for s in listed["sessions"]}
    assert legacy_sid in ids
    assert oc_sid in ids
