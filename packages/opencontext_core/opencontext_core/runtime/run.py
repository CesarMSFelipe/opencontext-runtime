"""RuntimeRun and run-result models.

Covers SPEC RC-003 (``RuntimeRun`` belongs to a session), RC-009
(``NodeResult`` evidence shape), and the runner result/next-action DTOs (RC-008).
Reuses ``models.run_envelope.ArtifactRef`` rather than redefining it (RC-014),
and attaches a per-run ``DecisionLog`` seam (RC-CONV).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.models.run_envelope import ArtifactRef
from opencontext_core.runtime.decisions import DecisionLog


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class RuntimeRun(BaseModel):
    """One execution of one workflow inside a session (book §8)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.run.v1"
    run_id: str
    session_id: str
    workflow_id: str
    status: str = "created"
    current_node: str | None = None
    started_at: str = Field(default_factory=_now_iso)
    completed_at: str | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    receipts: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)

    # Convergence seam (RC-CONV): every run can attach decision entries.
    decision_log: DecisionLog = Field(default_factory=DecisionLog)


class GateResult(BaseModel):
    """The outcome of a single gate evaluated during node execution."""

    model_config = ConfigDict(extra="forbid")

    gate: str
    passed: bool
    reason: str = ""


class NodeResult(BaseModel):
    """Evidence record for a single node execution (book §13, RC-009)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.node_result.v1"
    session_id: str
    run_id: str
    workflow_id: str
    node_id: str
    status: str
    summary: str = ""
    gates: list[GateResult] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)
    duration_ms: int = 0
    next_recommended: str | None = None
    error: str | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    receipts: list[str] = Field(default_factory=list)


class NextAction(BaseModel):
    """The runner's recommendation for what happens next."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["execute_node", "await_approval", "complete", "fail", "escalate"]
    node_id: str | None = None
    reason: str = ""


class RunResult(BaseModel):
    """The aggregate result of running (part of) a workflow run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    node_results: list[NodeResult] = Field(default_factory=list)
    # Carries the unchanged legacy ``HarnessRunner`` result when the runtime
    # wraps it (RC-013). Typed ``Any`` so the legacy dataclass passes through
    # byte-for-byte without re-modelling.
    legacy: Any | None = None
