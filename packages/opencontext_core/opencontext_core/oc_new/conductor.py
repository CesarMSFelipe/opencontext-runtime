"""OcNewConductor — drives the stateful oc-new flow."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from opencontext_core.compat import UTC
from opencontext_core.oc_new.flow import OC_NEW_FLOW
from opencontext_core.oc_new.models import (
    AgentHandoff,
    ChangeIdentity,
    HandoffBudget,
    NextAction,
    OcNewRunState,
    PhaseDefinition,
    PhaseState,
)
from opencontext_core.oc_new.store import OcNewStore
from opencontext_core.paths import StorageMode, resolve_workspace_path
from opencontext_core.workflow.phase_result import PhaseResultEnvelope

if TYPE_CHECKING:
    from opencontext_core.agentic.budget_controller import BudgetDecision
    from opencontext_core.agentic.config import AgenticFlowConfig
    from opencontext_core.memory.capture import MemoryCaptureService
    from opencontext_core.memory.phase_policy import PhaseMemoryPolicy
    from opencontext_core.workflow.leases import AgentCoordinationStore

_logger = logging.getLogger(__name__)


class _NoopCoordStore:
    """Drop-in stub returned when the real AgentCoordinationStore cannot be constructed.

    Every method is a silent no-op so callers never see an exception even if the
    underlying SQLite database is unavailable.
    """

    def acquire(self, *args: object, **kwargs: object) -> object:
        return type("_Lease", (), {"lease_id": "noop"})()

    def signal(self, *args: object, **kwargs: object) -> None:
        pass

    def release_by_run_phase(self, *args: object, **kwargs: object) -> None:
        pass


# DEPRECATED(2.0): adapted (losing) execution spine of the two-spine convergence; superseded
# by HarnessRunner->RuntimeApi. Still the live oc-new driver; remove when resume carry-over
# reaches parity on the HarnessRunner spine (milestone-C).
class OcNewConductor:
    def __init__(
        self,
        root: Path | str = ".",
        capture_service: MemoryCaptureService | None = None,
    ) -> None:
        self.root = Path(root)
        self.store = OcNewStore(self.root)
        self._capture_service = capture_service
        self.__coord_store: object | None = None  # backing attr for lazy property

    @property
    def _coord_store(self) -> AgentCoordinationStore:
        """Lazy-initialized AgentCoordinationStore backed by .opencontext/coordination.db.

        Construction is guarded so absence of the db directory never raises into
        the conductor flow — failure is deferred to the first operation and is
        caught there.
        """
        from opencontext_core.workflow.leases import AgentCoordinationStore

        if self.__coord_store is None:
            try:
                self.__coord_store = AgentCoordinationStore(
                    resolve_workspace_path(self.root, StorageMode.local) / "coordination.db"
                )
            except Exception:
                # Return a no-op fallback object so callers can proceed.
                self.__coord_store = _NoopCoordStore()
        return self.__coord_store  # type: ignore[return-value]

    def start(self, task: str, config: AgenticFlowConfig | None = None) -> OcNewRunState:
        """Start a new oc-new run, optionally with an AgenticFlowConfig.

        The config is persisted in OcNewRunState so that resume() is faithful
        to the original preset and flow-mode settings.
        """
        identity = ChangeIdentity.from_task(task)
        phases = [PhaseState(name=phase.name) for phase in OC_NEW_FLOW]
        state = OcNewRunState(identity=identity, task=task, phases=phases, config=config)
        state = self._advance(state)
        self.store.save(state)
        return state

    def resume(self, run_id: str) -> OcNewRunState:
        state = self.store.load(run_id)
        state = self._advance(state)
        self.store.save(state)
        return state

    def _load_required_phase_envelope(
        self,
        state: OcNewRunState,
        phase_name: str,
    ) -> PhaseResultEnvelope:
        """Load a phase-result envelope from the run directory.

        When ``require_phase_envelopes`` is True (the default) the envelope
        file MUST exist; its absence raises ``RuntimeError``.  When the flag
        is False and the file is absent a synthetic "passed" envelope is
        returned so the caller can continue without breaking.
        """
        run_dir = self.store.run_dir(state.identity.run_id)
        path = run_dir / f"phase-result.{phase_name}.json"

        require = True
        if state.config is not None:
            require = getattr(state.config, "require_phase_envelopes", True)

        if not path.exists():
            if require:
                raise RuntimeError(f"Phase envelope missing: phase-result.{phase_name}.json")
            return PhaseResultEnvelope(
                run_id=state.identity.run_id,
                change_id=state.identity.change_id,
                phase=phase_name,
                status="passed",
                duration_s=0.0,
            )

        env = PhaseResultEnvelope.model_validate_json(path.read_text(encoding="utf-8"))

        if env.phase != phase_name:
            raise RuntimeError(f"Envelope phase mismatch: {env.phase} != {phase_name}")

        return env

    def mark_done(
        self,
        run_id: str,
        phase_name: str,
        *,
        status: str = "passed",
        artifact_paths: list[str] | None = None,
        warnings: list[str] | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> OcNewRunState:
        state = self.store.load(run_id)
        phase = state.phase(phase_name)  # type: ignore[arg-type]
        resolved = artifact_paths
        resolved_warnings = warnings
        env = self._load_required_phase_envelope(state, phase_name)
        resolved = env.artifacts
        blocked_reason: str | None = None
        if not env.can_advance():
            # Override caller-supplied status when the envelope blocks advance.
            status = "failed" if env.status == "failed" else "blocked"
            blocked_reason = f"phase envelope status is {env.status}"
        if env.risks:
            resolved_warnings = list(resolved_warnings or []) + env.risks

        # NOTE: REQ-05 — validate declared artifacts exist on disk before marking passed.
        if status == "passed":
            phase_def = next((p for p in OC_NEW_FLOW if p.name == phase_name), None)
            if phase_def is not None:
                run_dir = self.store.run_dir(run_id)
                missing_artifacts = [
                    a for a in phase_def.required_artifacts if not (run_dir / a).exists()
                ]
                if missing_artifacts:
                    missing_str = ", ".join(missing_artifacts)
                    status = "blocked"
                    blocked_reason = f"Required artifacts missing: {missing_str}"
                    resolved_warnings = [
                        *(resolved_warnings or []),
                        blocked_reason,
                    ]

        # NOTE: REQ-P1.1 — disk-check envelope declared artifacts (D1: fail-closed).
        if status == "passed" and env.artifacts:
            run_dir = self.store.run_dir(run_id)
            declared_missing = [a for a in env.artifacts if not (run_dir / a).exists()]
            if declared_missing:
                missing_str = ", ".join(declared_missing)
                status = "blocked"
                blocked_reason = f"Declared artifacts missing on disk: {missing_str}"
                resolved_warnings = [
                    *(resolved_warnings or []),
                    blocked_reason,
                ]

        # NOTE: REQ-01b — fail-closed archive gate (only when still on track to pass).
        if phase_name == "archive" and status == "passed":
            from opencontext_core.oc_new.archive_gate import OcNewArchiveGate

            run_dir = self.store.run_dir(run_id)
            try:
                OcNewArchiveGate().assert_can_archive(run_dir)
            except RuntimeError as exc:
                status = "blocked"
                blocked_reason = str(exc)
                resolved_warnings = [*(resolved_warnings or []), str(exc)]

        updated = phase.model_copy(
            update={
                "status": status,
                "completed_at": datetime.now(tz=UTC),
                "artifact_paths": (resolved if resolved is not None else phase.artifact_paths),
                "warnings": resolved_warnings if resolved_warnings is not None else phase.warnings,
            }
        )
        state = self._replace_phase(state, updated)
        if blocked_reason is not None:
            state = state.model_copy(update={"blocked_reason": blocked_reason})

        # NOTE: Emit capture events for phase boundaries.
        self._emit_phase_capture(
            phase_name=phase_name,
            run_id=run_id,
            status=status,
        )

        self._record_phase_budget(
            run_id,
            phase_name,
            used_input_tokens=input_tokens,
            used_output_tokens=output_tokens,
        )

        # NOTE: REQ-2 — release the lease for this (run_id, phase) pair.
        # Fail-soft: any exception is logged and swallowed.
        try:
            self._coord_store.release_by_run_phase(run_id, phase_name)
        except Exception as _e:
            _logger.warning(
                "Lease release failed for phase %s (run %s): %s",
                phase_name,
                run_id,
                _e,
            )

        # NOTE: spec PR-004 REQ-06 / SDD-CONV — mirror the harness spine's uniform
        # per-phase decision receipt on the oc_new spine. One PhaseReceipt per
        # phase (id, status, artifacts, declared harnesses) written through the
        # PR-002 ReceiptStore. Advisory: never interrupts the conductor flow.
        self._write_phase_receipt(
            run_id=run_id,
            phase_name=phase_name,
            status=status,
            artifact_paths=resolved if resolved is not None else [],
            trace_id=getattr(state.identity, "trace_id", None),
        )

        if status == "blocked":
            state = state.model_copy(
                update={
                    "current_phase": phase_name,
                    "next_action": NextAction(
                        kind="blocked",
                        phase=phase_name,  # type: ignore[arg-type]
                        instruction=blocked_reason or f"{phase_name} blocked",
                    ),
                }
            )
            self.store.save(state)
            return state

        # NOTE: After tasks phase completes, produce a git work plan.
        if phase_name == "tasks" and state.config is not None:
            self._write_git_plan(state)
        # NOTE: After archive phase completes, emit the agentic receipt.
        if phase_name == "archive" and status in {"passed", "warning"}:
            self._write_receipt(state)
            # NOTE: PR6 — propose post-archive lessons (approval-gated, never auto-write).
            self.propose_archive_lessons(
                run_id=state.identity.run_id,
                change_id=state.identity.change_id,
                config=state.config,
                approved=self._lessons_approved(),
            )
        state = self._advance(state)
        self.store.save(state)
        return state

    def _advance(self, state: OcNewRunState) -> OcNewRunState:
        for phase_def in OC_NEW_FLOW:
            phase = state.phase(phase_def.name)
            if phase.status in {"passed", "warning", "skipped"}:
                continue

            missing = self._missing_artifacts(state, phase_def)
            if missing:
                return state.model_copy(
                    update={
                        "current_phase": phase_def.name,
                        "blocked_reason": f"missing artifacts: {', '.join(missing)}",
                        "next_action": NextAction(
                            kind="blocked",
                            phase=phase_def.name,
                            persona=phase_def.persona,
                            instruction=(
                                f"Cannot run {phase_def.name}; missing: {', '.join(missing)}"
                            ),
                        ),
                        "updated_at": datetime.now(tz=UTC),
                    }
                )

            # NOTE: Budget gate — check before emitting any NextAction.
            if state.config is not None:
                budget_decision = self._check_budget(state, phase_def.name)
                if not budget_decision.allowed:
                    state = state.model_copy(
                        update={
                            "current_phase": phase_def.name,
                            "blocked_reason": budget_decision.reason,
                            "updated_at": datetime.now(tz=UTC),
                        }
                    )
                    self.store.save(state)
                    return state.model_copy(
                        update={
                            "next_action": NextAction(
                                kind="blocked",
                                phase=phase_def.name,
                                persona=phase_def.persona,
                                instruction=f"Budget exhausted: {budget_decision.reason}",
                            ),
                        }
                    )
                # NOTE: G3 — ASK budget mode pauses flow for user confirmation.
                if budget_decision.should_ask_user:
                    return state.model_copy(
                        update={
                            "current_phase": phase_def.name,
                            "blocked_reason": None,
                            "next_action": NextAction(
                                kind="request_approval",
                                phase=phase_def.name,
                                persona=phase_def.persona,
                                instruction=(
                                    f"Budget confirmation required before {phase_def.name}: "
                                    f"{budget_decision.reason}"
                                ),
                            ),
                            "updated_at": datetime.now(tz=UTC),
                        }
                    )

            if phase_def.name == "approval":
                return state.model_copy(
                    update={
                        "current_phase": "approval",
                        "blocked_reason": None,
                        "next_action": NextAction(
                            kind="request_approval",
                            phase="approval",
                            persona=None,
                            instruction=(
                                "Show spec, design and tasks to the user. "
                                "Create approval.json before apply."
                            ),
                            expected_artifacts=["approval.json"],
                        ),
                        "updated_at": datetime.now(tz=UTC),
                    }
                )

            # NOTE: When a flow_mode is set, check if we should pause after this phase.
            if self._should_pause(state, phase_def.name):
                return state.model_copy(
                    update={
                        "current_phase": phase_def.name,
                        "blocked_reason": None,
                        "next_action": NextAction(
                            kind="request_approval",
                            phase=phase_def.name,
                            persona=phase_def.persona,
                            instruction=(
                                f"Flow mode requires pause before {phase_def.name}. "
                                "Confirm to continue."
                            ),
                        ),
                        "updated_at": datetime.now(tz=UTC),
                    }
                )

            # NOTE: G4 — validate approval.json content before spawning apply subagent.
            if phase_def.name == "apply":
                run_dir = resolve_workspace_path(self.root, StorageMode.local) / "runs" / state.identity.run_id
                approval_error = self._validate_approval_content(run_dir)
                if approval_error:
                    return state.model_copy(
                        update={
                            "current_phase": phase_def.name,
                            "blocked_reason": approval_error,
                            "next_action": NextAction(
                                kind="blocked",
                                phase=phase_def.name,
                                persona=phase_def.persona,
                                instruction=approval_error,
                            ),
                            "updated_at": datetime.now(tz=UTC),
                        }
                    )

            # NOTE: observe_only / engram_only / openspec_only skip code-execution phases.
            if not self._should_execute_code(state) and phase_def.name in {"apply"}:
                return state.model_copy(
                    update={
                        "current_phase": phase_def.name,
                        "blocked_reason": None,
                        "next_action": NextAction(
                            kind="observe_only",
                            phase=phase_def.name,
                            persona=phase_def.persona,
                            instruction=(f"Flow mode skips code execution for {phase_def.name}."),
                        ),
                        "updated_at": datetime.now(tz=UTC),
                    }
                )

            policy = self._memory_policy_for(phase_def.name)
            memory_backend = "local"
            if state.config is not None:
                memory_backend = state.config.memory_mode.value
            mem_metadata: dict[str, object] = {
                "backend": memory_backend,
                "read_layers": [layer.value for layer in policy.read_layers] if policy else [],
                "write_layers": [layer.value for layer in policy.write_layers] if policy else [],
                "key": state.identity.memory_key,
            }

            # NOTE: Emit PHASE_START capture event before returning spawn action.
            self._emit_phase_start_capture(
                phase_name=phase_def.name,
                run_id=state.identity.run_id,
            )

            # NOTE: REQ-2 — acquire a lease and emit STARTED for this phase.
            # Fail-soft: any exception is logged and swallowed; it must NEVER
            # propagate into the flow.
            lease_metadata: dict[str, str] | None = None
            try:
                from opencontext_core.workflow.signals import AgentSignalKind

                _lease = self._coord_store.acquire(
                    phase_def.persona or "user",
                    state.identity.run_id,
                    phase_def.name,
                )
                self._coord_store.signal(_lease.lease_id, AgentSignalKind.STARTED)
                lease_metadata = {
                    "lease_id": _lease.lease_id,
                    "expires_at": _lease.expires_at.isoformat(),
                }
            except Exception as _e:
                _logger.warning(
                    "Lease acquire/signal failed for phase %s (run %s): %s",
                    phase_def.name,
                    state.identity.run_id,
                    _e,
                )

            # NOTE: D3 — build deterministic context_report_ref and full AgentHandoff.
            context_report_ref = (
                f".opencontext/runs/{state.identity.run_id}/{phase_def.name}.context.json"
            )
            handoff = AgentHandoff(
                run_id=state.identity.run_id,
                change_id=state.identity.change_id,
                trace_id=state.identity.trace_id,
                memory_key=state.identity.memory_key,
                task=state.task or "",
                phase=phase_def.name,
                persona=phase_def.persona or "",
                skill=phase_def.skill or "",
                # SDD-CONV: name the inputs this phase will consume so the handoff
                # artifact is an explicit input contract for the next persona.
                required_inputs=list(phase_def.required_artifacts),
                expected_outputs=list(phase_def.expected_artifacts),
                allowed_tools=list(phase_def.required_tools),
                context_report_ref=context_report_ref,
                budget=self._handoff_budget(state, phase_def.name),
            )
            # SDD-CONV: persist the handoff as a PersonaHandoff artifact on disk so
            # the phase transition leaves an inspectable input-naming record.
            self._write_handoff_artifact(state, phase_def.name, handoff)
            metadata: dict[str, object] = {
                "memory": mem_metadata,
                "context_report_ref": context_report_ref,
                "result_schema": "opencontext.phase_result.v1",
                "handoff": handoff.model_dump(mode="json"),
            }
            if lease_metadata is not None:
                metadata["lease"] = lease_metadata

            return state.model_copy(
                update={
                    "current_phase": phase_def.name,
                    "blocked_reason": None,
                    "next_action": NextAction(
                        kind="spawn_subagent",
                        phase=phase_def.name,
                        persona=phase_def.persona,
                        instruction=(
                            f"Run {phase_def.skill} as {phase_def.persona}. "
                            f"Use memory key {state.identity.memory_key}. "
                            f"Produce: {', '.join(phase_def.expected_artifacts)}."
                        ),
                        required_tools=phase_def.required_tools,
                        expected_artifacts=phase_def.expected_artifacts,
                        metadata=metadata,
                    ),
                    "updated_at": datetime.now(tz=UTC),
                }
            )

        return state.model_copy(
            update={
                "current_phase": None,
                "blocked_reason": None,
                "next_action": NextAction(kind="done", instruction="oc-new completed."),
                "updated_at": datetime.now(tz=UTC),
            }
        )

    def _should_pause(self, state: OcNewRunState, phase_name: str) -> bool:
        """Return True when the configured flow_mode requires a pause before *phase_name*."""
        if state.config is None:
            return False
        from opencontext_core.agentic.modes import should_pause_after_phase

        return should_pause_after_phase(state.config.flow_mode, phase_name)

    def _should_execute_code(self, state: OcNewRunState) -> bool:
        """Return False for observe/engram/openspec-only flow modes."""
        if state.config is None:
            return True
        from opencontext_core.agentic.modes import should_execute_code

        return should_execute_code(state.config.flow_mode)

    def _write_handoff_artifact(
        self, state: OcNewRunState, phase_name: str, handoff: AgentHandoff
    ) -> None:
        """Persist a phase handoff as a PersonaHandoff artifact (SDD-CONV).

        Projects the :class:`AgentHandoff` onto the PR-006 ``PersonaHandoff`` view
        (book field names) and writes it to ``handoff.<phase>.json`` in the run
        dir, naming the inputs the phase will consume. Advisory: any failure is
        logged and swallowed so it never interrupts the conductor flow.
        """
        try:
            from opencontext_core.personas.handoff import PersonaHandoff

            persona_handoff = PersonaHandoff.from_agent_handoff(handoff)
            run_dir = self.store.run_dir(state.identity.run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / f"handoff.{phase_name}.json").write_text(
                persona_handoff.model_dump_json(indent=2), encoding="utf-8"
            )
        except Exception as exc:
            _logger.warning(
                "Handoff artifact write failed for phase %s (run %s): %s",
                phase_name,
                state.identity.run_id,
                exc,
            )

    def _write_phase_receipt(
        self,
        run_id: str,
        phase_name: str,
        status: str,
        artifact_paths: list[str],
        trace_id: str | None = None,
    ) -> None:
        """Mirror the harness spine's per-phase receipt on the oc_new spine.

        Writes one :class:`PhaseReceipt` (spec PR-004 REQ-06 / SDD-CONV) through
        the PR-002 ``ReceiptStore`` into the run dir, recording the phase id, its
        resolved status, the artifacts it produced and the phase's declared
        required harnesses. Advisory: any failure is logged and swallowed so it
        never interrupts the conductor flow.
        """
        try:
            from opencontext_core.harness.receipt_store import ReceiptStore
            from opencontext_core.models.receipt import PhaseReceipt

            phase_def = next((p for p in OC_NEW_FLOW if p.name == phase_name), None)
            required = list(getattr(phase_def, "required_harnesses", []) or [])
            run_dir = self.store.run_dir(run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            receipt = PhaseReceipt(
                run_id=run_id,
                phase=phase_name,
                status=status,
                artifact_refs=list(artifact_paths or []),
                required_harnesses=required,
                trace_id=trace_id,
            )
            ReceiptStore(run_dir).write(receipt)
        except Exception as exc:
            _logger.warning(
                "Phase receipt write failed for phase %s (run %s): %s",
                phase_name,
                run_id,
                exc,
            )

    def _write_receipt(self, state: OcNewRunState) -> None:
        """Build and write AgenticReceipt to the run directory after archive."""
        import json

        from opencontext_core.agentic.receipt import AgenticReceipt, sha256_file, sha256_tree

        run_dir = resolve_workspace_path(self.root, StorageMode.local) / "runs" / state.identity.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        config = state.config
        flow_mode = config.flow_mode.value if config else "automatic"
        openspec_mode = config.openspec_mode.value if config else "off"
        budget_mode = config.budget_mode.value if config else "warn"
        git_mode = config.git_mode.value if config else "none"

        receipt = AgenticReceipt(
            run_id=state.identity.run_id,
            change_id=state.identity.change_id,
            flow_mode=flow_mode,
            openspec_mode=openspec_mode,
            budget_mode=budget_mode,
            git_mode=git_mode,
            status="complete",
            completed_phases=list(state.completed_phases()),
            budget_ledger_hash=sha256_file(run_dir / "budget_ledger.json"),
            git_work_plan_hash=sha256_file(run_dir / "git_plan.json"),
            memory_snapshot_hash=sha256_tree(run_dir),
            # NOTE: G5 — v2 identity fields populated from runtime state.
            trace_id=getattr(getattr(state, "identity", None), "trace_id", None) or None,
            task=getattr(state, "task", None) or None,
            memory_mode=config.memory_mode.value if config else None,
            preset=(config.preset.value if config and config.preset is not None else None),
        )
        receipt_path = run_dir / "receipt.json"
        receipt_path.write_text(json.dumps(receipt.model_dump(), indent=2))

    def _write_git_plan(self, state: OcNewRunState) -> None:
        """Build a GitWorkPlan and persist it to the run directory."""
        import json

        from opencontext_core.agentic.git_plan import GitWorkPlanner

        if state.config is None:
            return
        git_mode = state.config.git_mode
        task_phases = [p for p in state.phases if p.status in {"passed", "warning"}]
        tasks: list[str] = [p.name for p in task_phases]
        planner = GitWorkPlanner()
        plan = planner.plan(
            change_id=state.identity.change_id,
            tasks=tasks,
            mode=git_mode,
        )
        run_dir = resolve_workspace_path(self.root, StorageMode.local) / "runs" / state.identity.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        git_plan_path = run_dir / "git_plan.json"
        git_plan_path.write_text(json.dumps(plan.model_dump(), indent=2))

    def _check_budget(self, state: OcNewRunState, phase_name: str) -> BudgetDecision:
        """Return a BudgetDecision for *phase_name* given current run state."""
        from opencontext_core.agentic.budget import BudgetLedger
        from opencontext_core.agentic.budget_controller import BudgetController

        ledger_path = (
            resolve_workspace_path(self.root, StorageMode.local) / "runs" / state.identity.run_id / "budget_ledger.json"
        )
        if ledger_path.exists():
            ledger = BudgetLedger.model_validate_json(ledger_path.read_text())
        else:
            mode = getattr(state.config, "budget_mode", "warn")
            ledger = BudgetLedger(mode=str(mode))

        return BudgetController().decide(state.config, ledger, phase_name)

    def _handoff_budget(self, state: OcNewRunState, phase_name: str) -> HandoffBudget:
        """Build budget metadata for agent handoff."""
        phase_budget = int(getattr(state.config, "phase_budget", 0) or 0)
        used_before = 0
        ledger_path = (
            resolve_workspace_path(self.root, StorageMode.local) / "runs" / state.identity.run_id / "budget_ledger.json"
        )
        if ledger_path.exists():
            try:
                from opencontext_core.agentic.budget import BudgetLedger

                used_before = BudgetLedger.model_validate_json(ledger_path.read_text()).used_total
            except Exception:
                used_before = 0
        budget_mode = str(getattr(getattr(state.config, "budget_mode", "warn"), "value", "warn"))
        return HandoffBudget(
            phase_budget=phase_budget,
            used_before_phase=used_before,
            max_output_tokens=phase_budget // 2 if phase_budget else 0,
            budget_mode=budget_mode,
        )

    def _memory_policy_for(self, phase: str) -> PhaseMemoryPolicy | None:
        """Return the memory read/write policy for *phase*, or None if unknown."""
        from opencontext_core.memory.phase_policy import PHASE_MEMORY_POLICY

        return PHASE_MEMORY_POLICY.get(phase)

    def _record_phase_budget(
        self,
        run_id: str,
        phase: str,
        *,
        used_input_tokens: int = 0,
        used_output_tokens: int = 0,
        compression_savings: int = 0,
    ) -> None:
        """Append a PhaseBudget entry to the run's budget_ledger.json."""
        import json

        from opencontext_core.agentic.budget import BudgetLedger, PhaseBudget

        ledger_path = resolve_workspace_path(self.root, StorageMode.local) / "runs" / run_id / "budget_ledger.json"
        if ledger_path.exists():
            ledger = BudgetLedger.model_validate_json(ledger_path.read_text())
        else:
            ledger = BudgetLedger(mode="adaptive")

        entry = PhaseBudget(
            phase=phase,
            used_input_tokens=used_input_tokens,
            used_output_tokens=used_output_tokens,
            compression_savings=compression_savings,
        )
        ledger = ledger.add_phase(entry)
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(ledger.model_dump(), indent=2))

    def _emit_phase_capture(
        self,
        phase_name: str,
        run_id: str,
        status: str,
    ) -> None:
        """Emit PHASE_END (and optionally VERIFY_FAILURE) capture events."""
        if self._capture_service is None:
            return
        try:
            from opencontext_core.memory.capture import CaptureEventKind, MemoryCaptureEvent

            end_event = MemoryCaptureEvent(
                kind=CaptureEventKind.PHASE_END,
                phase=phase_name,
                run_id=run_id,
                content=f"Phase {phase_name} completed with status={status}",
            )
            self._capture_service.capture(end_event)

            if status == "failed":
                failure_event = MemoryCaptureEvent(
                    kind=CaptureEventKind.VERIFY_FAILURE,
                    phase=phase_name,
                    run_id=run_id,
                    content=f"Phase {phase_name} failed",
                )
                self._capture_service.capture(failure_event)
        except Exception:
            # NOTE: Capture errors must never interrupt the main conductor flow.
            pass

    def _emit_phase_start_capture(self, phase_name: str, run_id: str) -> None:
        """Emit PHASE_START capture event."""
        if self._capture_service is None:
            return
        try:
            from opencontext_core.memory.capture import CaptureEventKind, MemoryCaptureEvent

            start_event = MemoryCaptureEvent(
                kind=CaptureEventKind.PHASE_START,
                phase=phase_name,
                run_id=run_id,
                content=f"Phase {phase_name} starting",
            )
            self._capture_service.capture(start_event)
        except Exception:
            pass

    def _replace_phase(self, state: OcNewRunState, updated: PhaseState) -> OcNewRunState:
        return state.model_copy(
            update={
                "phases": [updated if p.name == updated.name else p for p in state.phases],
                "updated_at": datetime.now(tz=UTC),
            }
        )

    def _validate_approval_content(self, run_dir: Path) -> str | None:
        """Return a block reason if approval.json is missing or not approved, else None.

        Fail-closed: parse errors and IO errors also return a block reason.
        Approval is valid when data.get("status") == "approved" OR data.get("approved") is True.
        """
        approval_path = run_dir / "approval.json"
        if not approval_path.exists():
            # Existence is checked separately by _missing_artifacts; if we reach
            # here without the file, treat it as unapproved (fail-closed).
            return "approval.json not found"
        try:
            data = json.loads(approval_path.read_text())
        except (json.JSONDecodeError, OSError):
            return "approval.json is not valid JSON"
        if data.get("status") == "approved" or data.get("approved") is True:
            return None
        return (
            f"approval.json not approved: "
            f"status={data.get('status')!r}, approved={data.get('approved')!r}"
        )

    def _missing_artifacts(self, state: OcNewRunState, phase_def: PhaseDefinition) -> list[str]:
        run_dir = resolve_workspace_path(self.root, StorageMode.local) / "runs" / state.identity.run_id
        spec_dir = self.root / "openspec" / "changes" / state.identity.change_id
        missing: list[str] = []
        for artifact in phase_def.required_artifacts:
            if not (run_dir / artifact).exists() and not (spec_dir / artifact).exists():
                missing.append(artifact)
        return missing

    # NOTE: PR6 — additive post-archive lesson proposal (approval-gated).
    def _lessons_approved(self) -> bool:
        """Return True iff the user has explicitly opted in to lesson capture.

        Honour the ``OPENCONTEXT_CAPTURE_LESSONS`` env-var as a structured
        opt-in. AUTOMATIC flow without this flag MUST NOT auto-write.
        """
        import os

        return os.environ.get("OPENCONTEXT_CAPTURE_LESSONS", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def propose_archive_lessons(
        self,
        run_id: str,
        change_id: str,
        *,
        approved: bool = False,
        config: AgenticFlowConfig | None = None,
        lessons: list[str] | None = None,
    ) -> Path | None:
        """Approval-gated post-archive lesson proposal.

        Returns the path of the written proposal on success; None when
        skipped. NEVER writes under ``~/.claude/skills/``; the project
        namespace ``.opencontext/runs/<run_id>/lessons.json`` is used.
        """
        if not approved:
            return None
        import json

        run_dir = resolve_workspace_path(self.root, StorageMode.local) / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        proposal_path = run_dir / "lessons.json"
        # NOTE: fail-closed — assert the resolved path never touches the user home.
        home = Path.home()
        try:
            proposal_path.resolve().relative_to(home.resolve())
        except ValueError:
            pass
        else:
            raise RuntimeError("propose_archive_lessons would write under the user home; aborting")
        flow_mode = getattr(getattr(config, "flow_mode", None), "value", "automatic")
        payload = {
            "run_id": run_id,
            "change_id": change_id,
            "flow_mode": flow_mode,
            "lessons": list(lessons or []),
        }
        proposal_path.write_text(json.dumps(payload, indent=2))
        return proposal_path
