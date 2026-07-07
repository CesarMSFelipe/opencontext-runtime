"""CLI decision-log inspection (RB-009).

``opencontext decisions show <run_id>`` lists every recorded RuntimeDecision
with its kind, selected value, and rationale for a run.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def _seed_oc_flow_run(tmp_path: Path, run_id: str, decisions: list[dict]) -> None:
    """Persist an OC Flow run dir (state.json + decisions.json), no run.json."""
    run_dir = tmp_path / ".opencontext" / "sessions" / "sess-flow" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
    (run_dir / "decisions.json").write_text(json.dumps({"decisions": decisions}), encoding="utf-8")


def test_decisions_show_reads_oc_flow_decisions(tmp_path: Path, capsys) -> None:
    # An OC Flow run records decisions in decisions.json, not run.json.
    _seed_oc_flow_run(
        tmp_path,
        "run-flow",
        [
            {
                "kind": "next_node",
                "selected": "plan",
                "governed_by": "state_machine",
                "rationale": "graph routes init -> plan",
                "alternatives": [],
            }
        ],
    )
    handle_decisions(
        SimpleNamespace(decisions_action="show", run_id="run-flow", root=str(tmp_path), json=False)
    )
    out = capsys.readouterr().out
    assert "next_node: plan" in out
    assert "graph routes init -> plan" in out


def test_decisions_show_existing_run_without_decisions_is_honest(tmp_path: Path, capsys) -> None:
    # The run EXISTS on disk but recorded no decisions -> honest, not "Run not found".
    _seed_oc_flow_run(tmp_path, "run-empty", [])
    handle_decisions(
        SimpleNamespace(decisions_action="show", run_id="run-empty", root=str(tmp_path), json=False)
    )
    out = capsys.readouterr().out
    assert "no decisions recorded" in out
    assert "Run not found" not in out


def test_decisions_show_missing_run_still_errors(tmp_path: Path, capsys) -> None:
    _seed_oc_flow_run(tmp_path, "run-real", [])
    with pytest.raises(SystemExit) as exc:
        handle_decisions(
            SimpleNamespace(decisions_action="show", run_id="ghost", root=str(tmp_path), json=False)
        )
    assert exc.value.code == 1
    assert "Run not found: ghost" in capsys.readouterr().err


def test_decisions_list_empty_reports_clearly(tmp_path: Path, capsys) -> None:
    handle_decisions(SimpleNamespace(decisions_action="list", root=str(tmp_path), json=False))
    assert "No runs with recorded decisions" in capsys.readouterr().out


@pytest.fixture(autouse=True)
def _legacy_local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """This module asserts the legacy in-repo layout; pin local storage mode."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
