"""FastAPI schemas for the OpenContext Runtime adapter."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IndexRequest(BaseModel):
    """Request body for project indexing."""

    model_config = ConfigDict(extra="forbid")

    root: str = Field(default=".", description="Project root to index.")


class IndexResponse(BaseModel):
    """Response body for project indexing."""

    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(description="Indexed project name.")
    files: int = Field(ge=0, description="Number of indexed files.")
    symbols: int = Field(ge=0, description="Number of extracted symbols.")
    technology_profiles: list[str] = Field(description="Detected technology profiles.")


class SetupRequest(BaseModel):
    """Request body for non-CLI project setup."""

    model_config = ConfigDict(extra="forbid")

    root: str = Field(default=".", description="Project root to prepare.")
    write_config: bool = Field(
        default=True,
        description="Whether to create opencontext.yaml when it is missing.",
    )
    refresh_index: bool = Field(
        default=True,
        description="Whether to rebuild and persist the project manifest.",
    )


class SetupResponse(BaseModel):
    """Response body for non-CLI project setup."""

    model_config = ConfigDict(extra="forbid")

    root: str = Field(description="Prepared project root.")
    config_path: str = Field(description="OpenContext YAML configuration path.")
    workspace_path: str = Field(description="Project-local .opencontext workspace path.")
    manifest_path: str = Field(description="Persisted project manifest path.")
    files: int = Field(ge=0, description="Indexed file count.")
    symbols: int = Field(ge=0, description="Indexed symbol count.")
    technology_profiles: list[str] = Field(description="Detected technology profiles.")


class RunRequest(BaseModel):
    """Request body for workflow execution."""

    model_config = ConfigDict(extra="forbid")

    input: str = Field(description="User request.")
    workflow_name: str = Field(default="code_assistant", description="Workflow name.")


class RunResponse(BaseModel):
    """Response body for workflow execution."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(description="Generated answer.")
    trace_id: str = Field(description="Persisted trace id.")
    token_usage: dict[str, int] = Field(description="Token usage summary.")
    selected_context_count: int = Field(ge=0, description="Selected context item count.")


class TraceResponse(BaseModel):
    """Response body for trace lookup."""

    model_config = ConfigDict(extra="forbid")

    trace: dict[str, Any] = Field(description="Serialized runtime trace.")


class ManifestResponse(BaseModel):
    """Response body for project manifest lookup."""

    model_config = ConfigDict(extra="forbid")

    manifest: dict[str, Any] = Field(description="Serialized project manifest.")


class RepoMapResponse(BaseModel):
    """Response body for repository map lookup."""

    model_config = ConfigDict(extra="forbid")

    repo_map: str = Field(description="Rendered compact repo map.")


class ContextPackRequest(BaseModel):
    """Request body for context pack generation."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Retrieval query.")
    max_tokens: int | None = Field(default=None, gt=0, description="Optional pack budget.")


class ContextPackResponse(BaseModel):
    """Response body for context pack generation."""

    model_config = ConfigDict(extra="forbid")

    pack: dict[str, Any] = Field(description="Serialized context pack result.")


class PreparedContextRequest(BaseModel):
    """Request body for simple non-CLI context preparation."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Task or question to prepare context for.")
    root: str = Field(default=".", description="Project root to index when needed.")
    max_tokens: int | None = Field(default=None, gt=0, description="Optional context budget.")
    refresh_index: bool = Field(
        default=False,
        description="Whether to rebuild the persisted project manifest before retrieval.",
    )


class PreparedContextResponse(BaseModel):
    """Response body for persisted non-CLI context preparation."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(description="Persisted trace id for this context bundle.")
    context: str = Field(description="Compact redacted context text.")
    included_sources: list[str] = Field(description="Sources included in the context.")
    omitted_sources: list[str] = Field(description="Sources omitted from the context.")
    token_usage: dict[str, int] = Field(description="Context and prompt token accounting.")
    trust_decision: dict[str, str] = Field(description="Planner trust decision metadata.")
    fallback_actions: list[str] = Field(description="Planner fallback actions.")
    source_surfaces: list[str] = Field(description="Planner source surfaces represented.")


class VerifiedContextRequestBody(BaseModel):
    """Request body for one-shot verified context."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Task or question to prepare verified context for.")
    root: str | None = Field(default=None, description="Optional project root to index.")
    max_tokens: int | None = Field(default=None, gt=0, description="Optional context budget.")
    refresh_index: bool = Field(default=False, description="Whether to rebuild the local index.")
    include_memory: bool = Field(default=True, description="Whether local memory may be used.")
    include_vector: bool = Field(
        default=False,
        description="Whether configured vector search may be used.",
    )


class VerifiedContextResponse(BaseModel):
    """Response body for one-shot verified context."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(description="Trace id for this verification attempt.")
    context: str = Field(description="Rendered verified context text.")
    evidence: list[dict[str, Any]] = Field(description="Evidence used in the context.")
    memory: list[dict[str, Any]] = Field(description="Local memory evidence used in the context.")
    gates: list[dict[str, Any]] = Field(description="Verification gate summaries.")
    risk_level: str = Field(description="Deterministic local risk level.")
    trust_decision: dict[str, str] = Field(description="Planner trust outcome.")
    token_usage: dict[str, int] = Field(description="Token usage summary.")
    omitted_sources: list[str] = Field(description="Sources omitted with traceable reasons.")


class OrchestrateRequest(BaseModel):
    """Request body for orchestration planning."""

    model_config = ConfigDict(extra="forbid")

    requirements_path: str = Field(description="Path to requirements used for planning.")


class ValidateRequest(BaseModel):
    """Request body for safe validation planning."""

    model_config = ConfigDict(extra="forbid")

    profile: str = Field(default="generic", description="Validation profile.")


class AgentContextRequest(BaseModel):
    """Request body for agent-context export planning."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Task or question for the target agent.")
    root: str = Field(default=".", description="Project root to index when needed.")
    target: str = Field(default="generic", description="Target agent context format.")
    mode: str = Field(default="plan", description="Context mode.")
    max_tokens: int = Field(default=10000, gt=0, description="Maximum context budget.")
    refresh_index: bool = Field(
        default=False,
        description="Whether to rebuild the persisted project manifest before retrieval.",
    )


class ScaffoldResponse(BaseModel):
    """Generic response for scaffolded v0.1 endpoints."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="Endpoint implementation status.")
    result: dict[str, Any] = Field(description="Structured scaffold result.")
