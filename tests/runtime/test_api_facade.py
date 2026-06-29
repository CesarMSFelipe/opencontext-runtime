"""Tests for the RuntimeApi facade surface (SPEC RC-001)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.runtime.api import RunRequest, RuntimeApi, StartSessionRequest
from opencontext_core.runtime.session_store import SessionStore


class _FakeResult:
    def __init__(self, run_id: str = "sdd-legacy", status: str = "passed") -> None:
        self.run_id = run_id
        self.status = status


class _FakeHarness:
    def __init__(self, result: _FakeResult) -> None:
        self._result = result

    def run(self, workflow: str, task: str) -> _FakeResult:
        return self._result

    def schedule_phases(self, workflow: str) -> list[str]:
        return ["explore", "apply"]


class TestFacadeSurface:
    def test_exactly_eight_public_methods(self, tmp_path: Path) -> None:
        api = RuntimeApi(tmp_path)
        public = sorted(
            name for name in dir(api) if not name.startswith("_") and callable(getattr(api, name))
        )
        assert public == sorted(
            [
                "start_session",
                "run",
                "next",
                "observe",
                "apply",
                "inspect",
                "resume",
                "archive",
            ]
        )


class TestStartThenRun:
    def test_run_populates_active_run_id(self, tmp_path: Path) -> None:
        fake = _FakeHarness(_FakeResult())
        api = RuntimeApi(tmp_path, harness_factory=lambda root: fake)
        ref = api.start_session(StartSessionRequest(task="do x", root=str(tmp_path)))
        result = api.run(RunRequest(session_id=ref.session_id, workflow_id="sdd"))

        session = SessionStore(tmp_path).load_session(ref.session_id)
        assert session.active_run_id is not None
        assert result.run_id == session.active_run_id
