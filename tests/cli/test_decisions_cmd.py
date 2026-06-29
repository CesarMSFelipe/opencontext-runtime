"""CLI decision-log inspection (RB-009).

``opencontext decisions show <run_id>`` lists every recorded RuntimeDecision
with its kind, selected value, and rationale for a run.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from opencontext_cli.commands.decisions_cmd import handle_decisions
from opencontext_core.runtime.decisions import RuntimeDecision
from opencontext_core.runtime.run import RuntimeRun
from opencontext_core.runtime.session import RuntimeSession
from opencontext_core.runtime.session_store import SessionStore


def _seed(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.create_session(
        RuntimeSession(session_id="sess-1", root=str(tmp_path), task="t", profile="balanced")
    )
    run = RuntimeRun(run_id="run-1", session_id="sess-1", workflow_id="wf")
    run.decision_log.append(
        RuntimeDecision(
            kind="provider",
            chosen="mock:mock-llm",
            reason="default route for generate",
            run_id="run-1",
        )
    )
    run.decision_log.append(
        RuntimeDecision(
            kind="persona", chosen="oc-architect", reason="design phase", run_id="run-1"
        )
    )
    store.create_run(run)


def test_decisions_show_lists_every_decision(tmp_path: Path, capsys) -> None:
    _seed(tmp_path)
    handle_decisions(
        SimpleNamespace(decisions_action="show", run_id="run-1", root=str(tmp_path), json=False)
    )
    out = capsys.readouterr().out
    assert "provider: mock:mock-llm" in out
    assert "persona: oc-architect" in out
    assert "default route for generate" in out


def test_decisions_show_json(tmp_path: Path, capsys) -> None:
    _seed(tmp_path)
    handle_decisions(
        SimpleNamespace(decisions_action="show", run_id="run-1", root=str(tmp_path), json=True)
    )
    rows = json.loads(capsys.readouterr().out)
    assert {r["kind"] for r in rows} == {"provider", "persona"}
    assert all("selected" in r and "rationale" in r for r in rows)


def test_decisions_list_shows_runs_with_decisions(tmp_path: Path, capsys) -> None:
    _seed(tmp_path)
    handle_decisions(SimpleNamespace(decisions_action="list", root=str(tmp_path), json=True))
    rows = json.loads(capsys.readouterr().out)
    assert rows == [{"run_id": "run-1", "decisions": 2}]
