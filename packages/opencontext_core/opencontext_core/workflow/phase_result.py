"""PhaseResultEnvelope — canonical return shape for every phase handler.

PhaseResultEnvelope is the single contract phases honour when reporting
completion. The conductor inspects `can_advance()` (not raw status strings)
to decide whether to promote to the next phase. Adding a new advance-eligible
status here is the only place a developer needs to touch.

    return PhaseResultEnvelope(
        run_id=..., change_id=..., phase=..., status="passed", duration_s=...
    ).can_advance()
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PhaseResultStatus = Literal[
    "pending",
    "running",
    "passed",
    "warning",
    "failed",
    "blocked",
    "halted",
    "skipped",
    # PR-006 persona failure semantics (book doc 05 §13). `done`/`done_with_concerns`
    # advance (the latter only when gates allow — see `can_advance`); `needs_context`
    # routes to context retrieval and `failed_contract` returns to protocol/diagnosis,
    # so both are non-advancing.
    "done",
    "done_with_concerns",
    "needs_context",
    "failed_contract",
]

# `done` is the persona equivalent of `passed`; `done_with_concerns` of `warning`.
# `needs_context`/`failed_contract` are intentionally absent — they must NOT advance.
_ADVANCE_STATUSES: frozenset[str] = frozenset({"passed", "warning", "done", "done_with_concerns"})


class PhaseResultEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    run_id: str
    change_id: str
    phase: str
    status: PhaseResultStatus
    executive_summary: str = ""
    artifacts: list[str] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)
    duration_s: float
    error: str | None = None
    persona: str | None = None
    skill: str | None = None
    trace_id: str | None = None
    required_artifacts: list[str] = Field(default_factory=list)
    missing_artifacts: list[str] = Field(default_factory=list)
    context_report_path: str | None = None
    memory_report_path: str | None = None
    harness_report_path: str | None = None
    compliance_matrix_path: str | None = None
    verify_report_path: str | None = None
    risks: list[str] = Field(default_factory=list)
    next_recommended: str = ""

    def can_advance(self) -> bool:
        """True iff this phase cleared the gate and the conductor should promote."""
        if self.status not in _ADVANCE_STATUSES:
            return False
        if self.missing_artifacts:
            return False
        if self.error:
            return False
        return True


__all__ = ["PhaseResultEnvelope", "PhaseResultStatus"]


if __name__ == "__main__":  # NOTE: sanity check
    env = PhaseResultEnvelope(
        run_id="r", change_id="c", phase="apply", status="passed", duration_s=0.1
    )
    assert env.can_advance() is True
    failed = env.model_copy(update={"status": "failed"})
    assert failed.can_advance() is False
    print("workflow/phase_result.py self-check passed.")
