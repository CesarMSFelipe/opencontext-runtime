"""RunEnvelope — complete evidence record for one agentic run."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.models.context_contract import ContextContract

RunStatus = Literal["planned", "running", "passed", "warning", "failed", "blocked"]


class ModelUse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: str | None = None
    tool: str | None = None
    requested_provider: str | None = None
    requested_model: str | None = None
    actual_provider: str | None = None
    actual_model: str | None = None
    hint_honored: bool | None = None
    source: Literal["config", "mcp_sampling", "provider", "unknown"] = "unknown"


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    subject: str
    operation: str
    decision: Literal["allowed", "denied", "redacted", "skipped"]
    reason: str
    policy: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    status: Literal["passed", "warning", "failed", "denied", "skipped"]
    input_hash: str | None = None
    output_hash: str | None = None
    policy_decision_id: str | None = None
    trace_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    path: str
    sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunEnvelope(BaseModel):
    """Single evidence envelope for an OpenContext run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.run_envelope.v1"
    run_id: str
    workflow_id: str
    task: str
    status: RunStatus
    contract: ContextContract | None = None
    policy_decisions: list[PolicyDecision] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    model_uses: list[ModelUse] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
