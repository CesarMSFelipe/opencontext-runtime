"""OcNewConductor — drives the stateful oc-new flow."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from opencontext_core.compat import UTC
from opencontext_core.oc_new.flow import OC_NEW_FLOW
from opencontext_core.oc_new.models import (
    ChangeIdentity,
    NextAction,
    OcNewRunState,
    PhaseDefinition,
    PhaseState,
)
from opencontext_core.oc_new.store import OcNewStore

if TYPE_CHECKING:
    from opencontext_core.agentic.config import AgenticFlowConfig
    from opencontext_core.memory.phase_policy import PhaseMemoryPolicy


class OcNewConductor:
    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root)
        self.store = OcNewStore(self.root)

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
        updated = phase.model_copy(
            update={
                "status": status,
                "completed_at": datetime.now(tz=UTC),
                "artifact_paths": (
                    artifact_paths if artifact_paths is not None else phase.artifact_paths
                ),
                "warnings": warnings if warnings is not None else phase.warnings,
            }
        )
        state = self._replace_phase(state, updated)
        self._record_phase_budget(
            run_id,
            phase_name,
            used_input_tokens=input_tokens,
            used_output_tokens=output_tokens,
        )
        # NOTE: After tasks phase completes, produce a git work plan.
        if phase_name == "tasks" and state.config is not None:
            self._write_git_plan(state)
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
                            instruction=(
                                f"Flow mode skips code execution for {phase_def.name}."
                            ),
                        ),
                        "updated_at": datetime.now(tz=UTC),
                    }
                )

            policy = self._memory_policy_for(phase_def.name)
            memory_backend = "local"
            if state.config is not None:
                memory_backend = state.config.memory_mode.value
            mem_metadata: dict = {
                "backend": memory_backend,
                "read_layers": [l.value for l in policy.read_layers] if policy else [],
                "write_layers": [l.value for l in policy.write_layers] if policy else [],
                "key": state.identity.memory_key,
            }

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
                        metadata={"memory": mem_metadata},
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

    def _write_git_plan(self, state: OcNewRunState) -> None:
        """Build a GitWorkPlan and persist it to the run directory."""
        import json

        from opencontext_core.agentic.git_plan import GitWorkPlanner

        if state.config is None:
            return
        git_mode = state.config.git_mode
        task_phases = [p for p in state.phases if p.status in {"passed", "warning"}]
        tasks = [p.name for p in task_phases]
        planner = GitWorkPlanner()
        plan = planner.plan(
            change_id=state.identity.change_id,
            tasks=tasks,
            mode=git_mode,
        )
        run_dir = self.root / ".opencontext" / "runs" / state.identity.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        git_plan_path = run_dir / "git_plan.json"
        git_plan_path.write_text(json.dumps(plan.model_dump(), indent=2))

    def _check_budget(self, state: OcNewRunState, phase_name: str) -> object:
        """Return a BudgetDecision for *phase_name* given current run state."""
        from opencontext_core.agentic.budget import BudgetLedger
        from opencontext_core.agentic.budget_controller import BudgetController

        import json

        ledger_path = (
            self.root / ".opencontext" / "runs" / state.identity.run_id / "budget_ledger.json"
        )
        if ledger_path.exists():
            ledger = BudgetLedger.model_validate_json(ledger_path.read_text())
        else:
            mode = getattr(state.config, "budget_mode", "warn")
            ledger = BudgetLedger(mode=str(mode))

        return BudgetController().decide(state.config, ledger, phase_name)

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

        ledger_path = (
            self.root / ".opencontext" / "runs" / run_id / "budget_ledger.json"
        )
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

    def _replace_phase(self, state: OcNewRunState, updated: PhaseState) -> OcNewRunState:
        return state.model_copy(
            update={
                "phases": [
                    updated if p.name == updated.name else p
                    for p in state.phases
                ],
                "updated_at": datetime.now(tz=UTC),
            }
        )

    def _missing_artifacts(self, state: OcNewRunState, phase_def: PhaseDefinition) -> list[str]:
        run_dir = self.root / ".opencontext" / "runs" / state.identity.run_id
        spec_dir = self.root / "openspec" / "changes" / state.identity.change_id
        missing: list[str] = []
        for artifact in phase_def.required_artifacts:
            if not (run_dir / artifact).exists() and not (spec_dir / artifact).exists():
                missing.append(artifact)
        return missing
