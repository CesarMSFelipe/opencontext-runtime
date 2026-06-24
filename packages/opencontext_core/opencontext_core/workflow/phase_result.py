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
]

_ADVANCE_STATUSES: frozenset[str] = frozenset({"passed", "warning"})


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

    def can_advance(self) -> bool:
        """True iff this phase cleared the gate and the conductor should promote."""
        return self.status in _ADVANCE_STATUSES


__all__ = ["PhaseResultEnvelope", "PhaseResultStatus"]


if __name__ == "__main__":  # ponytail: tiny executable sanity check
    env = PhaseResultEnvelope(
        run_id="r", change_id="c", phase="apply", status="passed", duration_s=0.1
    )
    assert env.can_advance() is True
    failed = env.model_copy(update={"status": "failed"})
    assert failed.can_advance() is False
    print("workflow/phase_result.py self-check passed.")
