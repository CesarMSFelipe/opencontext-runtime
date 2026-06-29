"""RuntimeApi hardening — durable apply/resume/inspect (SPEC AVH-014 / B7).

These cover the CONFIRMED DEFECT: ``apply`` used to return ``applied=False``
("deferred to PR-002") and ``resume`` only flipped a status field. With
``runtime.durable_artifacts`` on, ``apply`` now checkpoints + applies + writes a
patch artifact and per-file receipts, ``resume`` validates the run manifest and
continues from the checkpoint (failing safe on a missing required artifact), and
``inspect`` surfaces artifacts / receipts / decision log. With the flag off the
PR-001 skeleton behaviour is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.agents.executor import ApplyEdit, ApplyOperation
from opencontext_core.harness.artifact_store import ArtifactStore
from opencontext_core.harness.receipt_store import ReceiptStore
from opencontext_core.harness.sessions import (
    ensure_layout,
    run_root,
    write_run_manifest,
)
from opencontext_core.models.run_manifest import ArtifactRef, RunManifest
from opencontext_core.runtime.api import (
    MutationRequest,
    RuntimeApi,
    StartSessionRequest,
)
from opencontext_core.runtime.decisions import RuntimeDecision
from opencontext_core.runtime.errors import RuntimeErrorCode, RuntimeFailure
from opencontext_core.runtime.session import SessionStatus
from opencontext_core.runtime.session_store import SessionStore


# --------------------------------------------------------------------- config
class _Runtime:
    def __init__(self, *, durable: bool) -> None:
        self.durable_artifacts = durable
        self.session_wrapper = True


class _Config:
    def __init__(self, *, durable: bool) -> None:
        self.runtime = _Runtime(durable=durable)


# -------------------------------------------------------------------- harness
class _FakeResult:
    def __init__(self, status: str = "passed") -> None:
        self.run_id = "fake"
        self.status = status


class _ResumeHarness:
    """Records the resume_from it was driven with (artifact-aware continuation)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def run(self, workflow: str, task: str, resume_from: str | None = None) -> _FakeResult:
        self.calls.append((workflow, task, resume_from))
        return _FakeResult()


def _durable_api(tmp_path: Path, harness: object | None = None) -> RuntimeApi:
    return RuntimeApi(
        tmp_path,
        config=_Config(durable=True),
        harness_factory=(lambda root: harness) if harness is not None else None,
    )


def _start(api: RuntimeApi, tmp_path: Path) -> str:
    ref = api.start_session(StartSessionRequest(task="fix bug", root=str(tmp_path)))
    return ref.session_id


def _create_edit() -> dict:
    return ApplyEdit(
        path="pkg/newmod.py",
        operation=ApplyOperation.CREATE_FILE,
        content="def add(a, b):\n    return a + b\n",
        reason="seed module",
        requirement_refs=["AVH-014"],
    ).model_dump(mode="json")


# --------------------------------------------------------------------- apply
class TestApplyDurable:
    def test_apply_creates_checkpoint_patch_receipt(self, tmp_path: Path) -> None:
        api = _durable_api(tmp_path)
        sid = _start(api, tmp_path)

        result = api.apply(sid, MutationRequest(kind="edit", payload={"edits": [_create_edit()]}))

        # applied=True only when all three stores accept the artifacts.
        assert result.applied is True
        assert result.status == "applied"
        assert result.checkpoint_id
        assert result.patch_artifact_id
        assert result.receipt_ids
        assert result.changed_files == ["pkg/newmod.py"]

        # The edit really landed on disk.
        assert (tmp_path / "pkg" / "newmod.py").read_text(encoding="utf-8").startswith("def add")

        # Durable evidence exists in the stores.
        run_dir = run_root(tmp_path, sid, result.run_id)
        assert (run_dir / "manifest.json").exists()
        assert list((run_dir / "checkpoints").glob("*.json"))
        assert list((run_dir / "patches").glob("*.diff"))

        patch_refs = ArtifactStore(run_dir).list_for_run(result.run_id)
        assert any(r.kind == "patch" for r in patch_refs)
        apply_receipts = ReceiptStore(run_dir).list_apply_receipts()
        assert len(apply_receipts) == 1
        assert apply_receipts[0].path == "pkg/newmod.py"
        assert apply_receipts[0].changed is True

    def test_apply_failure_raises_structured_error_not_silent_false(self, tmp_path: Path) -> None:
        api = _durable_api(tmp_path)
        sid = _start(api, tmp_path)

        # REPLACE_RANGE on a non-existent file: apply_edit raises → must surface a
        # typed RuntimeFailure, never a silent applied=False.
        bad = ApplyEdit(
            path="ghost.py",
            operation=ApplyOperation.REPLACE_RANGE,
            start_line=1,
            end_line=1,
            content="x = 1",
        ).model_dump(mode="json")

        with pytest.raises(RuntimeFailure) as excinfo:
            api.apply(sid, MutationRequest(kind="edit", payload={"edits": [bad]}))
        assert excinfo.value.code == RuntimeErrorCode.MUTATION_FAILED
        # Rolled back: the file was not created.
        assert not (tmp_path / "ghost.py").exists()

    def test_apply_empty_edits_is_honest_noop(self, tmp_path: Path) -> None:
        api = _durable_api(tmp_path)
        sid = _start(api, tmp_path)
        result = api.apply(sid, MutationRequest(kind="edit", payload={"edits": []}))
        assert result.applied is False
        assert result.status == "no-op"
        assert "no edits" in result.reason


# -------------------------------------------------------------------- resume
class TestResumeDurable:
    def test_resume_validates_manifest_and_continues_from_checkpoint(self, tmp_path: Path) -> None:
        harness = _ResumeHarness()
        api = _durable_api(tmp_path, harness=harness)
        sid = _start(api, tmp_path)

        # Produce a durable run (manifest + checkpoint + patch) to resume from.
        applied = api.apply(sid, MutationRequest(kind="edit", payload={"edits": [_create_edit()]}))
        prior_run_id = applied.run_id
        prior_dir = run_root(tmp_path, sid, prior_run_id)
        patch_path = next(iter((prior_dir / "patches").glob("*.diff")))
        before = patch_path.read_bytes()

        api.resume(sid)

        # Continuation drove the harness with resume_from = the prior run.
        assert harness.calls
        assert harness.calls[-1][2] == prior_run_id
        # Existing artifacts are not overwritten (continuation mints a fresh run).
        assert patch_path.read_bytes() == before

    def test_resume_fails_safe_on_missing_required_artifact(self, tmp_path: Path) -> None:
        harness = _ResumeHarness()
        api = _durable_api(tmp_path, harness=harness)
        sid = _start(api, tmp_path)

        # Hand-craft a durable run whose manifest references a REQUIRED artifact
        # that does not exist on disk.
        run_id = "sdd-deadbeef0001"
        ensure_layout(tmp_path, sid, run_id)
        run_dir = run_root(tmp_path, sid, run_id)
        manifest = RunManifest(
            session_id=sid,
            run_id=run_id,
            workflow_id="sdd",
            status="paused",
            artifacts=[
                ArtifactRef(
                    artifact_id="art-ghost",
                    run_id=run_id,
                    kind="spec",
                    path="artifacts/ghost.json",
                    required=True,
                )
            ],
        )
        write_run_manifest(run_dir, manifest)

        store = SessionStore(tmp_path)
        session = store.load_session(sid)
        session.active_run_id = run_id
        session.status = SessionStatus.paused
        store.save_session(session)

        with pytest.raises(RuntimeFailure) as excinfo:
            api.resume(sid)
        assert excinfo.value.code == RuntimeErrorCode.RESUME_FAILED
        # Fail-safe: no continuation was attempted and the status is unmutated.
        assert harness.calls == []
        assert store.load_session(sid).status == SessionStatus.paused

    def test_resume_without_durable_run_uses_legacy_flip(self, tmp_path: Path) -> None:
        # durable flag on, but no manifest for the active run → legacy flip path.
        api = _durable_api(tmp_path)
        sid = _start(api, tmp_path)
        store = SessionStore(tmp_path)
        session = store.load_session(sid)
        session.status = SessionStatus.paused
        store.save_session(session)

        state = api.resume(sid)
        assert state.status == str(SessionStatus.running)


# ------------------------------------------------------------------- inspect
class TestInspectDurable:
    def test_inspect_surfaces_artifacts_receipts_and_decision_log(self, tmp_path: Path) -> None:
        api = _durable_api(tmp_path)
        sid = _start(api, tmp_path)
        result = api.apply(sid, MutationRequest(kind="edit", payload={"edits": [_create_edit()]}))

        # Attach a decision-log entry to the run.
        store = SessionStore(tmp_path)
        run = store.load_run(sid, result.run_id)
        run.decision_log.append(
            RuntimeDecision(kind="provider", chosen="ollama", reason="local + cheap")
        )
        store.save_run(run)

        report = api.inspect(sid)

        assert any(a.kind == "patch" for a in report.artifacts)
        assert report.receipts  # apply receipts surfaced
        assert len(report.decision_log) == 1
        assert report.decision_log[0]["chosen"] == "ollama"


# ------------------------------------------------------- legacy (flag off)
class TestLegacyPathUnchanged:
    def test_apply_flag_off_records_intent_only(self, tmp_path: Path) -> None:
        api = RuntimeApi(tmp_path)  # no config → durable_artifacts defaults off
        sid = _start(api, tmp_path)
        result = api.apply(sid, MutationRequest(kind="edit", payload={"edits": [_create_edit()]}))
        assert result.applied is False
        assert result.reason == "durable mutation is deferred to PR-002"
        # No file written on the skeleton path.
        assert not (tmp_path / "pkg" / "newmod.py").exists()

    def test_inspect_flag_off_has_empty_durable_fields(self, tmp_path: Path) -> None:
        api = RuntimeApi(tmp_path)
        sid = _start(api, tmp_path)
        report = api.inspect(sid)
        assert report.artifacts == []
        assert report.receipts == []
        assert report.decision_log == []
