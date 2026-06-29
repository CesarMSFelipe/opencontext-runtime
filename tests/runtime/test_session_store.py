"""Tests for the on-disk session store and live state (SPEC RC-006)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.runtime.run import RuntimeRun
from opencontext_core.runtime.session import LiveState, RuntimeSession
from opencontext_core.runtime.session_store import SessionStore


def _session(sid: str = "sess-1") -> RuntimeSession:
    return RuntimeSession(session_id=sid, root="/proj", task="do x", profile="balanced")


class TestSessionLayout:
    def test_create_session_materialises_tree(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path)
        store.create_session(_session())

        base = tmp_path / ".opencontext" / "sessions" / "sess-1"
        assert (base / "session.json").exists()
        assert (base / "events.jsonl").exists()
        assert (base / "live-state.json").exists()

    def test_session_records_its_own_paths(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path)
        store.create_session(_session())
        loaded = store.load_session("sess-1")
        assert loaded.events_path.endswith("sess-1/events.jsonl")
        assert loaded.live_state_path.endswith("sess-1/live-state.json")
        assert loaded.artifacts_root.endswith("sess-1/runs")

    def test_run_written_under_runs_dir(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path)
        store.create_session(_session())
        store.create_run(RuntimeRun(run_id="sdd-9", session_id="sess-1", workflow_id="sdd"))
        run_json = tmp_path / ".opencontext" / "sessions" / "sess-1" / "runs" / "sdd-9" / "run.json"
        assert run_json.exists()
        assert store.load_run("sess-1", "sdd-9").run_id == "sdd-9"


class TestLiveState:
    def test_live_state_reflects_node_status_and_last_event(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path)
        store.create_session(_session())
        store.write_live_state(
            LiveState(
                session_id="sess-1",
                run_id="sdd-9",
                workflow="sdd",
                node="apply",
                status="running",
                last_event_id="evt-123",
            )
        )
        live = store.load_live_state("sess-1")
        assert live.node == "apply"
        assert live.status == "running"
        assert live.last_event_id == "evt-123"
