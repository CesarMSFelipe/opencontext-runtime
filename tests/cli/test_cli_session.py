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
