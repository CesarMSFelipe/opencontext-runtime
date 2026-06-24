"""Read-only projection of OcNewRunState for UX surfaces.

WorkflowState is derived on demand from OcNewRunState (single source of truth
in state.json). No third spine, no side effects.

    state = WorkflowState.project_from(run_state)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.oc_new.flow import OC_NEW_FLOW
from opencontext_core.oc_new.models import (
    NextActionKind,
    OcNewRunState,
    PhaseName,
    PhaseStatus,
)

PhaseNameAlias = PhaseName  # ponytail: narrow alias for UX consumers
PhaseStatusAlias = PhaseStatus
NextActionKindAlias = NextActionKind


class WorkflowPhase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: PhaseName
    status: PhaseStatus
    artifact_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowGate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: PhaseName | None
    blocked: bool
    reason: str | None = None


class WorkflowEvent(BaseModel):
    """Append-only timeline hook; not persisted by this slice."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    phase: PhaseName | None
    kind: Literal["phase_start", "phase_done", "blocked", "unblocked"]
    detail: str | None = None


class WorkflowState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    change_id: str
    trace_id: str
    task: str
    current_phase: PhaseName | None
    next_action_kind: NextActionKind | None
    blocked_reason: str | None
    phases: list[WorkflowPhase]
    gate: WorkflowGate

    @classmethod
    def project_from(cls, run_state: OcNewRunState) -> WorkflowState:
        """Pure: derive a WorkflowState from run_state without IO or mutation."""
        canonical = {p.name for p in OC_NEW_FLOW}
        projected = [
            WorkflowPhase(
                name=src.name,
                status=src.status,
                artifact_paths=list(src.artifact_paths),
                warnings=list(src.warnings),
                started_at=src.started_at,
                completed_at=src.completed_at,
            )
            for src in run_state.phases
            if src.name in canonical
        ]
        names = {p.name for p in projected}
        if names != canonical:
            raise ValueError(
                f"WorkflowState projection invalid — "
                f"unknown={sorted(names - canonical)}, missing={sorted(canonical - names)}"
            )

        blocked = run_state.blocked_reason is not None or any(
            p.status == "blocked" for p in projected
        )
        return cls(
            run_id=run_state.identity.run_id,
            change_id=run_state.identity.change_id,
            trace_id=run_state.identity.trace_id,
            task=run_state.task,
            current_phase=run_state.current_phase,
            next_action_kind=run_state.next_action.kind if run_state.next_action else None,
            blocked_reason=run_state.blocked_reason,
            phases=projected,
            gate=WorkflowGate(
                phase=run_state.current_phase if blocked else None,
                blocked=blocked,
                reason=run_state.blocked_reason,
            ),
        )


__all__ = [
    "NextActionKindAlias",
    "PhaseNameAlias",
    "PhaseStatusAlias",
    "WorkflowEvent",
    "WorkflowGate",
    "WorkflowPhase",
    "WorkflowState",
]


if __name__ == "__main__":  # ponytail: tiny executable sanity check
    from opencontext_core.oc_new.models import ChangeIdentity, NextAction, PhaseState

    state = OcNewRunState(
        identity=ChangeIdentity.from_task("selftest"),
        task="selftest",
        phases=[PhaseState(name=p.name) for p in OC_NEW_FLOW],
        current_phase="design",
        next_action=NextAction(kind="spawn_subagent", phase="design", instruction="x"),
    )
    proj = WorkflowState.project_from(state)
    assert len(proj.phases) == 10 and proj.next_action_kind == "spawn_subagent"
    print("workflow/state.py self-check passed.")