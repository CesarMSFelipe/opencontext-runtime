"""RuntimeApi — the workflow-neutral 8-method facade (SPEC RC-001/013).

All external interfaces (MCP / CLI / TUI / Studio) reach the runtime through
this facade. PR-001 implements:

* ``start_session`` / ``run`` / ``next`` fully, including the ``HarnessRunner``
  compatibility wrapper (run brackets the legacy run with a session + events,
  returning the legacy result unchanged);
* ``observe`` / ``archive`` as session-level skeletons.

``apply`` / ``resume`` / ``inspect`` are hardened against the PR-002 durable
stores behind the ``runtime.durable_artifacts`` flag (SPEC AVH-014 / B7):

* with the flag **on**, ``apply`` checkpoints the target files, applies the
  edits, writes a patch artifact + per-file ``ApplyReceipt`` + a run manifest,
  and returns ``applied=True`` with refs (a store/apply rejection raises a typed
  ``RuntimeFailure`` — never a silent ``applied=False``); ``resume`` validates
  the run manifest + artifact checksums via :class:`ResumeManager` (failing safe
  with no state mutated when a required artifact is missing) and then continues
  execution from the last checkpoint; ``inspect`` surfaces the run's artifacts,
  receipts and decision log;
* with the flag **off** (default) all three keep their PR-001 behaviour, so the
  legacy path and its tests are byte-identical.

The ``session_wrapper`` flag (default on) makes ``run`` revertible to a direct
``HarnessRunner.run()`` call that writes no session tree.
"""

from __future__ import annotations

import importlib.util
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC, StrEnum
from opencontext_core.runtime.errors import RuntimeErrorCode, RuntimeFailure
from opencontext_core.runtime.event_bus import JsonlEventBus
from opencontext_core.runtime.events import make_event
from opencontext_core.runtime.modes import RuntimeMode
from opencontext_core.runtime.run import NextAction, RunResult, RuntimeRun
from opencontext_core.runtime.session import (
    ExecutionProfile,
    LiveState,
    RuntimeSession,
    SessionStatus,
)
from opencontext_core.runtime.session_store import SessionStore


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _detect_capabilities() -> dict[str, bool]:
    """Detect local tooling at session start (RC-CONV capability snapshot).

    Real detection: ``pytest`` import availability (test gate), a ``ruff``/``git``
    executable on PATH (lint / vcs). The keys are always present so callers can
    rely on the snapshot's shape regardless of the environment.
    """
    return {
        "pytest": importlib.util.find_spec("pytest") is not None,
        "ruff": shutil.which("ruff") is not None,
        "git": shutil.which("git") is not None,
    }


# --------------------------------------------------------------------- DTOs
class StartSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str
    root: str | None = None
    profile: str = "balanced"


class SessionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: str
    session_path: str


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    workflow_id: str = "sdd"
    task: str | None = None
    mode: RuntimeMode = RuntimeMode.run_to_completion


class RuntimeEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    status: str = "ok"
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class MutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applied: bool
    status: str
    reason: str = ""
    # Durable refs (B7/AVH-014). Populated only on the ``durable_artifacts`` path
    # when the mutation is actually applied; empty on the legacy/skeleton path.
    run_id: str = ""
    checkpoint_id: str = ""
    patch_artifact_id: str = ""
    receipt_ids: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)


class InspectionScope(StrEnum):
    session = "session"
    run = "run"
    events = "events"
    live_state = "live_state"


class ArtifactSummary(BaseModel):
    """A durable artifact surfaced by :meth:`RuntimeApi.inspect` (B7/AVH-014)."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    kind: str
    path: str


class ReceiptSummary(BaseModel):
    """A durable receipt surfaced by :meth:`RuntimeApi.inspect` (B7/AVH-014)."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    kind: str | None = None
    path: str = ""


class InspectionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: str
    active_run_id: str | None = None
    run_count: int = 0
    event_count: int = 0
    node: str | None = None
    message: str = ""
    # Durable evidence for the active run (B7/AVH-014). Empty when no durable
    # run tree exists (legacy / skeleton path).
    artifacts: list[ArtifactSummary] = Field(default_factory=list)
    receipts: list[ReceiptSummary] = Field(default_factory=list)
    decision_log: list[dict[str, Any]] = Field(default_factory=list)


class SessionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: str
    active_run_id: str | None = None
    node: str | None = None
    message: str = ""
    last_event_id: str | None = None


class ArchiveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    archived: bool
    status: str


# --------------------------------------------------------------------- facade
class RuntimeApi:
    """The stable, workflow-neutral runtime boundary (exactly 8 methods)."""

    def __init__(
        self,
        root: Path | str = ".",
        *,
        config: Any = None,
        session_wrapper: bool | None = None,
        harness_factory: Any = None,
    ) -> None:
        self._root = Path(root)
        self._config = config
        self._store = SessionStore(self._root)
        self._harness_factory = harness_factory
        # The flag is, in priority order: explicit arg > config.runtime.session_wrapper
        # > default True. Read defensively so an absent config block is harmless
        # (config.py is intentionally not modified in PR-001).
        runtime_cfg = getattr(config, "runtime", None)
        if session_wrapper is not None:
            self._session_wrapper = session_wrapper
        else:
            self._session_wrapper = bool(getattr(runtime_cfg, "session_wrapper", True))
        # B7/AVH-014: the durable apply/resume/inspect path is gated by the same
        # ``runtime.durable_artifacts`` flag the harness uses. Off (default) keeps
        # the PR-001 skeleton behaviour. Read defensively so an absent config block
        # is harmless.
        self._durable_artifacts = bool(getattr(runtime_cfg, "durable_artifacts", False))

    # ------------------------------------------------------------- method 1
    def start_session(self, request: StartSessionRequest) -> SessionRef:
        session_id = f"sess-{uuid4().hex[:12]}"
        root = request.root or str(self._root)
        capabilities = _detect_capabilities()
        session = RuntimeSession(
            session_id=session_id,
            root=root,
            task=request.task,
            profile=request.profile,
            capabilities=capabilities,
            capability_snapshot=capabilities,
            execution_profile=ExecutionProfile(name=request.profile),
            config_snapshot=self._config_snapshot(),
        )
        self._store.create_session(session)
        bus = self._store.event_bus(session_id)
        bus.publish(
            make_event(
                session_id=session_id,
                type="session.created",
                status="ok",
                message="session created",
                metadata={"profile": request.profile},
            )
        )
        return SessionRef(
            session_id=session_id,
            status=str(session.status),
            session_path=str(self._store.session_dir(session_id)),
        )

    # ------------------------------------------------------------- method 2
    def run(self, request: RunRequest) -> RunResult:
        # Wrapper disabled: call HarnessRunner.run() directly; no session writes.
        if not self._session_wrapper:
            harness = self._make_harness(self._root)
            legacy = harness.run(request.workflow_id, request.task or "")
            return RunResult(
                run_id=str(getattr(legacy, "run_id", "legacy")),
                status=self._legacy_status(legacy),
                legacy=legacy,
            )

        try:
            session = self._store.load_session(request.session_id)
        except FileNotFoundError as exc:
            raise RuntimeFailure(
                RuntimeErrorCode.RESUME_FAILED,
                f"session not found: {request.session_id}",
                recoverable=False,
                next_action="call start_session before run",
            ) from exc

        task = request.task or session.task
        return self._execute_workflow_run(session, request.workflow_id, task)

    def _execute_workflow_run(
        self,
        session: RuntimeSession,
        workflow_id: str,
        task: str,
        *,
        resume_from: str | None = None,
    ) -> RunResult:
        """Bracket one ``HarnessRunner`` execution with a session run + events.

        Shared by :meth:`run` (fresh run) and :meth:`resume` (continuation: pass
        ``resume_from`` so the harness skips already-completed phases and carries
        over the prior run's artifacts instead of overwriting them).
        """
        run_id = f"{workflow_id}-{uuid4().hex[:12]}"
        run = RuntimeRun(
            run_id=run_id,
            session_id=session.session_id,
            workflow_id=workflow_id,
            status="running",
        )
        self._store.create_run(run)
        session.active_run_id = run_id
        session.status = SessionStatus.running
        self._store.save_session(session)

        bus = self._store.event_bus(session.session_id)
        bus.publish(
            make_event(
                session_id=session.session_id,
                run_id=run_id,
                workflow_id=workflow_id,
                type="run.created",
                status="ok",
                message="run created",
            )
        )
        started = bus.publish(
            make_event(
                session_id=session.session_id,
                run_id=run_id,
                workflow_id=workflow_id,
                type="workflow.started",
                status="running",
                message=task,
            )
        )
        self._store.write_live_state(
            LiveState(
                session_id=session.session_id,
                run_id=run_id,
                workflow=workflow_id,
                node="workflow",
                status="running",
                message="workflow started",
                last_event_id=started.event_id,
            )
        )

        harness = self._make_harness(Path(session.root))
        try:
            if resume_from is not None:
                legacy = harness.run(workflow_id, task, resume_from=resume_from)
            else:
                legacy = harness.run(workflow_id, task)
        except Exception as exc:
            self._finalize(session, run, bus, status="failed", message=str(exc))
            raise RuntimeFailure(
                RuntimeErrorCode.PROVIDER_FAILED,
                f"workflow execution failed: {exc}",
                recoverable=True,
                next_action="inspect the run and retry",
            ) from exc

        status = self._legacy_status(legacy)
        self._finalize(session, run, bus, status=status, message="workflow finished")
        return RunResult(run_id=run_id, status=run.status, legacy=legacy)

    # ------------------------------------------------------------- method 3
    def next(self, session_id: str) -> NextAction:
        session = self._store.load_session(session_id)
        if session.active_run_id is None:
            return NextAction(kind="complete", reason="no active run")
        run = self._store.load_run(session_id, session.active_run_id)
        if run.status == "failed":
            return NextAction(kind="fail", reason="active run failed")
        if run.status == "completed":
            return NextAction(kind="complete", reason="active run completed")
        if run.current_node:
            return NextAction(kind="execute_node", node_id=run.current_node)
        return NextAction(kind="complete", reason="active run finished")

    # ------------------------------------------------------------- method 4
    def observe(self, session_id: str, event: RuntimeEventInput) -> SessionState:
        session = self._store.load_session(session_id)
        bus = self._store.event_bus(session_id)
        published = bus.publish(
            make_event(
                session_id=session_id,
                run_id=session.active_run_id,
                type=event.type,
                status=event.status,
                message=event.message,
                metadata=event.metadata,
            )
        )
        return self._session_state(session, last_event_id=published.event_id)

    # ------------------------------------------------------------- method 5
    def apply(self, session_id: str, mutation: MutationRequest) -> ApplyResult:
        session = self._store.load_session(session_id)
        bus = self._store.event_bus(session_id)
        bus.publish(
            make_event(
                session_id=session_id,
                run_id=session.active_run_id,
                type="mutation.requested",
                status="recorded",
                message=mutation.kind,
                metadata={"kind": mutation.kind},
            )
        )
        if not self._durable_artifacts:
            # Legacy skeleton path: record intent only (PR-001 behaviour).
            return ApplyResult(
                applied=False,
                status="recorded",
                reason="durable mutation is deferred to PR-002",
            )
        # B7/AVH-014: durable apply — checkpoint, apply the edits, write a patch
        # artifact + per-file ApplyReceipts + the run manifest.
        return self._durable_apply(session, mutation, bus)

    def _durable_apply(
        self, session: RuntimeSession, mutation: MutationRequest, bus: JsonlEventBus
    ) -> ApplyResult:
        """Apply ``mutation``'s edits durably (checkpoint → apply → patch+receipts).

        ``mutation.payload['edits']`` is a list of
        :class:`~opencontext_core.agents.executor.ApplyEdit` dicts (the shipped,
        schema-validated edit model — no new edit shape). A failed apply restores
        the checkpoint and raises a typed :class:`RuntimeFailure` — it never
        returns ``applied=False`` silently (SPEC AVH-014).
        """
        from opencontext_core.agentic.receipt import sha256_file
        from opencontext_core.agents.executor import (
            ApplyEdit,
            ApplyOperation,
            apply_edit,
        )
        from opencontext_core.harness.artifact_store import ArtifactStore
        from opencontext_core.harness.checkpoint import CheckpointManager
        from opencontext_core.harness.receipt_store import ReceiptStore
        from opencontext_core.harness.sessions import (
            build_run_manifest,
            build_unified_diff,
            ensure_layout,
            next_patch_path,
            write_run_manifest,
        )
        from opencontext_core.models.receipt import ApplyReceipt

        root = Path(session.root)
        session_id = session.session_id

        raw_edits = mutation.payload.get("edits", [])
        try:
            edits = [
                e if isinstance(e, ApplyEdit) else ApplyEdit.model_validate(e) for e in raw_edits
            ]
        except (ValueError, TypeError) as exc:
            raise RuntimeFailure(
                RuntimeErrorCode.MUTATION_FAILED,
                f"mutation edits failed schema validation: {exc}",
                recoverable=False,
                next_action="emit a schema-valid ApplyEdit set",
            ) from exc

        if not edits:
            # Honest no-op: nothing to checkpoint or apply. Not a store rejection.
            return ApplyResult(
                applied=False,
                status="no-op",
                reason="mutation payload has no edits",
            )

        # Resolve (or mint) the run this mutation belongs to so inspect/resume can
        # find its durable evidence.
        run_id = session.active_run_id
        if not run_id:
            run_id = f"apply-{uuid4().hex[:12]}"
            self._store.create_run(
                RuntimeRun(
                    run_id=run_id,
                    session_id=session_id,
                    workflow_id=mutation.kind or "apply",
                    status="running",
                )
            )
            session.active_run_id = run_id
            self._store.save_session(session)

        run_dir = ensure_layout(root, session_id, run_id)

        # Snapshot exactly the files about to change BEFORE touching them.
        targets = [(root / edit.path).resolve() for edit in edits]
        checkpoint = CheckpointManager(root).create(
            targets, session_id=session_id, run_id=run_id, source="apply"
        )
        if checkpoint is None:  # pragma: no cover - guarded by the empty-edit check
            raise RuntimeFailure(
                RuntimeErrorCode.MUTATION_FAILED,
                "checkpoint store rejected the mutation (no target files)",
                recoverable=False,
            )
        cp_model = CheckpointManager(root).model(checkpoint, session_id=session_id, run_id=run_id)
        checkpoint_path = run_dir / "checkpoints" / f"{cp_model.checkpoint_id}.json"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(cp_model.model_dump_json(indent=2), encoding="utf-8")

        # Apply the edits. Any failure restores the checkpoint and raises — never a
        # silent applied=False (SPEC AVH-014: failure must be structured).
        try:
            for edit in edits:
                apply_edit(root, edit)
        except Exception as exc:
            checkpoint.restore()
            raise RuntimeFailure(
                RuntimeErrorCode.MUTATION_FAILED,
                f"apply failed and rolled back to checkpoint: {exc}",
                recoverable=True,
                next_action="inspect the run and retry with a valid edit set",
            ) from exc

        artifact_store = ArtifactStore(run_dir)
        receipt_store = ReceiptStore(run_dir)

        patch_text = build_unified_diff(checkpoint)
        patch_path = next_patch_path(run_dir)
        patch_path.write_text(patch_text, encoding="utf-8")
        diff_rel = patch_path.relative_to(run_dir).as_posix()
        try:
            patch_ref = artifact_store.register_file(
                patch_path,
                kind="patch",
                run_id=run_id,
                session_id=session_id,
                media_type="text/x-diff",
                produced_by="apply",
                metadata={"checkpoint_id": cp_model.checkpoint_id},
            )
        except Exception as exc:
            checkpoint.restore()
            raise RuntimeFailure(
                RuntimeErrorCode.MUTATION_FAILED,
                f"artifact store rejected the patch and the apply was rolled back: {exc}",
                recoverable=False,
            ) from exc

        before = cp_model.checksums
        receipt_ids: list[str] = []
        changed_files: list[str] = []
        for edit, target in zip(edits, targets, strict=True):
            key = str(target)
            created = edit.operation == ApplyOperation.CREATE_FILE or key not in before
            checksum_after = sha256_file(target)
            checksum_before = before.get(key)
            receipt = ApplyReceipt(
                path=edit.path,
                operation="create" if created else "modify",
                changed=created or checksum_before != checksum_after,
                checksum_before=checksum_before,
                checksum_after=checksum_after,
                diff_path=diff_rel,
                reason=edit.reason or mutation.kind,
                requirement_refs=list(edit.requirement_refs),
            )
            receipt_store.write(receipt)
            receipt_ids.append(receipt.receipt_id)
            changed_files.append(edit.path)

        manifest = build_run_manifest(
            run_dir,
            session_id=session_id,
            run_id=run_id,
            workflow_id=mutation.kind or "apply",
            status="applied",
            events_path=str(self._store.events_jsonl(session_id)),
        )
        write_run_manifest(run_dir, manifest)

        bus.publish(
            make_event(
                session_id=session_id,
                run_id=run_id,
                type="mutation.applied",
                status="applied",
                message=mutation.kind,
                metadata={
                    "checkpoint_id": cp_model.checkpoint_id,
                    "patch_artifact_id": patch_ref.artifact_id,
                    "changed_files": changed_files,
                },
            )
        )
        return ApplyResult(
            applied=True,
            status="applied",
            reason=f"applied {len(changed_files)} edit(s)",
            run_id=run_id,
            checkpoint_id=cp_model.checkpoint_id,
            patch_artifact_id=patch_ref.artifact_id,
            receipt_ids=receipt_ids,
            changed_files=changed_files,
        )

    # ------------------------------------------------------------- method 6
    def inspect(
        self, session_id: str, scope: InspectionScope = InspectionScope.session
    ) -> InspectionReport:
        session = self._store.load_session(session_id)
        events_path = self._store.events_jsonl(session_id)
        event_count = 0
        if events_path.exists():
            event_count = sum(
                1 for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()
            )
        runs_dir = self._store.runs_dir(session_id)
        run_count = 0
        if runs_dir.exists():
            run_count = sum(1 for child in runs_dir.glob("*") if child.is_dir())
        node: str | None = None
        message = ""
        try:
            live = self._store.load_live_state(session_id)
            node = live.node
            message = live.message
        except FileNotFoundError:
            pass

        # B7/AVH-014: surface the active run's durable artifacts, receipts and
        # decision log when a durable run tree exists. Read-only and additive —
        # empty lists when there is no durable evidence (legacy path).
        artifacts, receipts, decision_log = self._durable_evidence(
            session_id, session.active_run_id
        )
        return InspectionReport(
            session_id=session_id,
            status=str(session.status),
            active_run_id=session.active_run_id,
            run_count=run_count,
            event_count=event_count,
            node=node,
            message=message,
            artifacts=artifacts,
            receipts=receipts,
            decision_log=decision_log,
        )

    def _durable_evidence(
        self, session_id: str, run_id: str | None
    ) -> tuple[list[ArtifactSummary], list[ReceiptSummary], list[dict[str, Any]]]:
        """Collect the durable artifacts/receipts/decision-log for a run (B7)."""
        artifacts: list[ArtifactSummary] = []
        receipts: list[ReceiptSummary] = []
        decision_log: list[dict[str, Any]] = []
        if not run_id:
            return artifacts, receipts, decision_log

        from opencontext_core.harness.artifact_store import ArtifactStore
        from opencontext_core.harness.receipt_store import ReceiptStore
        from opencontext_core.harness.sessions import run_root

        run_dir = run_root(self._root, session_id, run_id)
        if run_dir.exists():
            for ref in ArtifactStore(run_dir).list_for_run(run_id):
                artifacts.append(
                    ArtifactSummary(artifact_id=ref.artifact_id, kind=ref.kind, path=ref.path)
                )
            store = ReceiptStore(run_dir)
            rel = store.path.relative_to(run_dir).as_posix() if store.path.exists() else ""
            for rcpt in store.list_all():
                receipts.append(
                    ReceiptSummary(
                        receipt_id=rcpt.receipt_id,
                        kind=getattr(rcpt, "kind", None),
                        path=rel,
                    )
                )
        try:
            run = self._store.load_run(session_id, run_id)
            decision_log = [d.model_dump(mode="json") for d in run.decision_log.entries]
        except FileNotFoundError:
            pass
        return artifacts, receipts, decision_log

    # ------------------------------------------------------------- method 7
    def resume(self, session_id: str) -> SessionState:
        session = self._store.load_session(session_id)
        if self._durable_artifacts and session.active_run_id:
            resumed = self._durable_resume(session)
            if resumed is not None:
                return resumed
        # Legacy skeleton path: flip a paused/awaiting session back to running.
        if session.status in (SessionStatus.paused, SessionStatus.waiting_for_approval):
            session.status = SessionStatus.running
            self._store.save_session(session)
        bus = self._store.event_bus(session_id)
        published = bus.publish(
            make_event(
                session_id=session_id,
                run_id=session.active_run_id,
                type="session.resumed",
                status=str(session.status),
                message="session resumed",
            )
        )
        return self._session_state(session, last_event_id=published.event_id)

    def _durable_resume(self, session: RuntimeSession) -> SessionState | None:
        """Validate the run manifest + artifacts, then continue from the checkpoint.

        Returns ``None`` (so :meth:`resume` falls back to the legacy flip) when the
        active run has no durable manifest to validate. Fails safe — raising a
        typed :class:`RuntimeFailure` with no state mutated — when a ``required``
        artifact is missing or fails its checksum (SPEC AVH-014 / RES-02).
        """
        from opencontext_core.harness.resume import ResumeIntegrityError, ResumeManager
        from opencontext_core.harness.sessions import run_root

        session_id = session.session_id
        prior_run_id = session.active_run_id or ""
        run_dir = run_root(self._root, session_id, prior_run_id)
        if not (run_dir / "manifest.json").exists():
            return None  # nothing durable to resume → legacy flip

        try:
            validation = ResumeManager(run_dir).validate()
        except ResumeIntegrityError as exc:
            raise RuntimeFailure(
                RuntimeErrorCode.RESUME_FAILED,
                f"resume integrity check failed: {exc}",
                recoverable=False,
                next_action="restore the missing/corrupt artifact or re-run from scratch",
            ) from exc

        bus = self._store.event_bus(session_id)
        bus.publish(
            make_event(
                session_id=session_id,
                run_id=prior_run_id,
                type="session.resumed",
                status="running",
                message="resume validated — continuing from checkpoint",
                metadata={
                    "resumed_from": prior_run_id,
                    "rehydrated_artifacts": len(validation.rehydrated),
                    "decision_log_entries": len(validation.decision_log_entries),
                    "warnings": validation.warnings,
                },
            )
        )

        # Continue execution from the last checkpoint: a fresh continuation run
        # skips the prior run's completed phases and carries over (never
        # overwrites) its artifacts.
        workflow_id = validation.manifest.workflow_id or "sdd"
        self._execute_workflow_run(
            session,
            workflow_id,
            session.task or "",
            resume_from=prior_run_id,
        )
        session = self._store.load_session(session_id)
        return self._session_state(session)

    # ------------------------------------------------------------- method 8
    def archive(self, session_id: str) -> ArchiveResult:
        session = self._store.load_session(session_id)
        session.status = SessionStatus.archived
        self._store.save_session(session)
        bus = self._store.event_bus(session_id)
        published = bus.publish(
            make_event(
                session_id=session_id,
                run_id=session.active_run_id,
                type="session.archived",
                status="archived",
                message="session archived",
            )
        )
        self._store.write_live_state(
            LiveState(
                session_id=session_id,
                run_id=session.active_run_id,
                status=str(session.status),
                message="session archived",
                last_event_id=published.event_id,
            )
        )
        return ArchiveResult(session_id=session_id, archived=True, status=str(session.status))

    # ----------------------------------------------------------- auxiliaries (commit-006)
    # Amendment A1: the three auxiliaries ``simulate``, ``get_health``,
    # ``decide`` ride alongside the 8-method session contract. They are
    # NOT a replacement for the session-first API; they are additional
    # helpers whose real bodies land in follow-up work. Stubs here raise
    # ``NotImplementedError`` so callers learn at call time, not at import.
    def simulate(self, plan: Any) -> Any:
        """Provider-free dry-run preview (commit-006 stub)."""
        raise NotImplementedError("RuntimeApi.simulate: stub in commit-006")

    def get_health(self) -> dict[str, Any]:
        """Aggregated runtime health snapshot (commit-006 stub)."""
        raise NotImplementedError("RuntimeApi.get_health: stub in commit-006")

    def decide(self, prompt: Any) -> dict[str, Any]:
        """Advisory decision request (commit-006 stub)."""
        raise NotImplementedError("RuntimeApi.decide: stub in commit-006")

    # ----------------------------------------------------------- internals
    def _finalize(
        self,
        session: RuntimeSession,
        run: RuntimeRun,
        bus: JsonlEventBus,
        *,
        status: str,
        message: str,
    ) -> None:
        run.status = status
        run.completed_at = _now_iso()
        self._store.save_run(run)
        if status == "failed":
            session.status = SessionStatus.failed
            event_type = "workflow.failed"
        else:
            session.status = SessionStatus.completed
            event_type = "workflow.completed"
        self._store.save_session(session)
        published = bus.publish(
            make_event(
                session_id=session.session_id,
                run_id=run.run_id,
                workflow_id=run.workflow_id,
                type=event_type,
                status=status,
                message=message,
            )
        )
        self._store.write_live_state(
            LiveState(
                session_id=session.session_id,
                run_id=run.run_id,
                workflow=run.workflow_id,
                node=None,
                status=status,
                message=message,
                last_event_id=published.event_id,
            )
        )

    def _session_state(
        self, session: RuntimeSession, *, last_event_id: str | None = None
    ) -> SessionState:
        node: str | None = None
        message = ""
        try:
            live = self._store.load_live_state(session.session_id)
            node = live.node
            message = live.message
        except FileNotFoundError:
            pass
        return SessionState(
            session_id=session.session_id,
            status=str(session.status),
            active_run_id=session.active_run_id,
            node=node,
            message=message,
            last_event_id=last_event_id,
        )

    def _make_harness(self, root: Path | str) -> Any:
        if self._harness_factory is not None:
            return self._harness_factory(Path(root))
        from opencontext_core.harness.runner import HarnessRunner

        return HarnessRunner(root=Path(root))

    @staticmethod
    def _legacy_status(legacy: Any) -> str:
        raw = getattr(legacy, "status", None)
        value = getattr(raw, "value", raw)
        text = str(value).lower() if value is not None else "completed"
        if text in ("failed", "blocked", "error"):
            return "failed"
        if text == "warning":
            return "completed_with_warnings"
        if text == "skipped":
            return "scaffolded"
        return "completed"

    def _config_snapshot(self) -> dict[str, Any]:
        # Best-effort, lightweight snapshot; full config capture is out of scope.
        if self._config is None:
            return {}
        return {"session_wrapper": self._session_wrapper}
