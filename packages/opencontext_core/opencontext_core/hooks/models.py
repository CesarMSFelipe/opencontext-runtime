"""Hook lifecycle data models — slice 5 (CAP5.Hook).

Pure data layer for the agentic runtime hook lifecycle. A hook is any callable
``(HookInput) -> HookDecision``; this module owns the *contract* only.

Orchestration concerns (registering hooks against ``HookEvent`` values,
dispatching them from the conductor, deciding when HALT short-circuits a
phase) live outside this module so the contract stays conductor-free and
trivially testable. Spec CAP5.Hook demands "Hooks MUST be invocable without
mutating conductor state" — that invariant is preserved by keeping
``HookInput`` an immutable Pydantic model.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class HookEvent(StrEnum):
    """Lifecycle event a hook can be registered against."""

    PHASE_START = "phase_start"
    PHASE_END = "phase_end"
    RUN_START = "run_start"
    RUN_END = "run_end"


class HookDecision(StrEnum):
    """Decision returned by a hook for the conductor to act on."""

    PROCEED = "proceed"
    HALT = "halt"


class HookInput(BaseModel):
    """Structured payload delivered to a hook at dispatch time.

    Immutable (Pydantic v2 ``BaseModel`` + ``model_config = frozen=True``)
    so dispatching hooks cannot mutate conductor state — a CAP5.Hook invariant.
    """

    model_config = {"frozen": True}

    phase_name: str | None = Field(
        default=None,
        description="Phase name for phase-scoped hooks; None for run-scoped events.",
    )
    run_id: str = Field(description="Stable identifier of the active run.")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form event-specific payload; typed by caller.",
    )


__all__ = ["HookDecision", "HookEvent", "HookInput"]


if __name__ == "__main__":  # NOTE: tiny executable sanity check
    assert {e.name for e in HookEvent} == {"PHASE_START", "PHASE_END", "RUN_START", "RUN_END"}
    assert {d.name for d in HookDecision} == {"PROCEED", "HALT"}
    inp = HookInput(phase_name="spec", run_id="run-1")
    assert inp.phase_name == "spec" and inp.payload == {}
    print("hooks/models.py self-check passed.")
