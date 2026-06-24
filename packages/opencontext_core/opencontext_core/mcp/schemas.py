"""Structured output schemas for MCP tool results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ToolStatus = Literal["passed", "warning", "failed", "denied", "skipped"]


class ToolWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolPolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["allowed", "denied", "redacted", "skipped"]
    reason: str
    policy: str = "ToolPermissionPolicy"


class ToolResultEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.mcp_tool_result.v1"
    tool: str
    status: ToolStatus
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[ToolWarning] = Field(default_factory=list)
    policy: ToolPolicyDecision | None = None
    trace_id: str | None = None
    receipt_id: str | None = None
