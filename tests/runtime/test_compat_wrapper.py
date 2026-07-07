"""Golden tests for the HarnessRunner compatibility wrapper (SPEC RC-013)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.runtime.api import RunRequest, RuntimeApi, StartSessionRequest
from opencontext_core.runtime.errors import RuntimeErrorCode, RuntimeFailure
from opencontext_core.runtime.session_store import SessionStore


class _FakeResult:
    def __init__(self, run_id: str = "sdd-legacy", status: str = "passed") -> None:
        self.run_id = run_id
        self.status = status


class _FakeHarness:
    def __init__(self, result: _FakeResult) -> None:
        self._result = result
        self.calls: list[tuple[str, str]] = []

    def run(self, workflow: str, task: str) -> _FakeResult:
        self.calls.append((workflow, task))
        return self._result

    def schedule_phases(self, workflow: str) -> list[str]:
        return ["explore", "apply"]


def _events_text(tmp_path: Path, session_id: str) -> str:
    return (tmp_path / ".opencontext" / "sessions" / session_id / "events.jsonl").read_text(
        encoding="utf-8"
    )


class TestWrapperOn:
    def test_legacy_result_preserved_and_events_emitted(self, tmp_path: Path) -> None:
        sentinel = _FakeResult(run_id="sdd-xyz", status="passed")
        fake = _FakeHarness(sentinel)
        api = RuntimeApi(tmp_path, session_wrapper=True, harness_factory=lambda root: fake)

        ref = api.start_session(StartSessionRequest(task="do x", root=str(tmp_path)))
        result = api.run(RunRequest(session_id=ref.session_id, workflow_id="sdd"))

        # The legacy result is returned unchanged (same object identity).
        assert result.legacy is sentinel
        assert result.status == "completed"
        assert fake.calls == [("sdd", "do x")]

        text = _events_text(tmp_path, ref.session_id)
        assert "workflow.started" in text
        assert "workflow.completed" in text

    def test_failure_path_records_failed_event_and_status(self, tmp_path: Path) -> None:
        fake = _FakeHarness(_FakeResult(run_id="sdd-bad", status="failed"))
        api = RuntimeApi(tmp_path, session_wrapper=True, harness_factory=lambda root: fake)

        ref = api.start_session(StartSessionRequest(task="do x", root=str(tmp_path)))
        result = api.run(RunRequest(session_id=ref.session_id, workflow_id="sdd"))

        assert result.status == "failed"
        text = _events_text(tmp_path, ref.session_id)
        assert "workflow.failed" in text
        run = SessionStore(tmp_path).load_run(ref.session_id, result.run_id)
        assert run.status == "failed"

    def test_run_without_session_raises_typed_error(self, tmp_path: Path) -> None:
        fake = _FakeHarness(_FakeResult())
        api = RuntimeApi(tmp_path, session_wrapper=True, harness_factory=lambda root: fake)
        with pytest.raises(RuntimeFailure) as excinfo:
            api.run(RunRequest(session_id="does-not-exist", workflow_id="sdd", task="t"))
        assert excinfo.value.code == RuntimeErrorCode.RESUME_FAILED
        # No run.json should have been written.
        assert not (tmp_path / ".opencontext" / "sessions" / "does-not-exist").exists()


class TestWrapperOff:
    def test_disabled_calls_harness_directly_without_session_writes(self, tmp_path: Path) -> None:
        sentinel = _FakeResult(run_id="sdd-direct", status="passed")
        fake = _FakeHarness(sentinel)
        api = RuntimeApi(tmp_path, session_wrapper=False, harness_factory=lambda root: fake)

        result = api.run(RunRequest(session_id="ignored", workflow_id="sdd", task="do x"))

        assert result.legacy is sentinel
        assert fake.calls == [("sdd", "do x")]
        assert not (tmp_path / ".opencontext" / "sessions").exists()


@pytest.fixture(autouse=True)
def _legacy_local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """This module asserts the legacy in-repo layout; pin local storage mode."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
