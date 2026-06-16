"""Evidence planning contracts for converged retrieval surfaces."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from opencontext_core.compat import StrEnum
from opencontext_core.models.context import DataClassification


class RetrievalSurface(StrEnum):
    """Supported caller surfaces for evidence planning."""

    RUNTIME = "runtime"
    CLI = "cli"
    API = "api"
    WORKFLOW = "workflow"
    AGENT_TOOL = "agent_tool"


class FreshnessStatus(StrEnum):
    """Freshness states attached before context packing."""

    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class RiskLevel(StrEnum):
    """Deterministic local risk level for verified context."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class GateSummary(BaseModel):
    """Serializable verification gate summary."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Gate name.")
    passed: bool = Field(description="Whether the gate passed.")
    reason: str = Field(description="Deterministic gate reason.")
    risks: list[str] = Field(default_factory=list, description="Risk codes for failed gates.")


class VerifiedContextRequest(BaseModel):
    """Provider-neutral request for one-shot verified context."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Natural-language context request.")
    root: Path | None = Field(default=None, description="Optional project root for indexing.")
    max_tokens: int | None = Field(default=None, gt=0, description="Optional context budget.")
    refresh_index: bool = Field(default=False, description="Whether to rebuild local index first.")
    include_memory: bool = Field(default=True, description="Whether local memory may be consulted.")
    include_vector: bool = Field(
        default=False,
        description="Whether configured vector search may be used.",
    )

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value


class VerifiedContextResult(BaseModel):
    """Provider-neutral result for one-shot verified context."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(description="Trace id for this verification attempt.")
    context: str = Field(description="Rendered verified context text.")
    evidence: list[EvidenceItem] = Field(description="Evidence used in the context.")
    memory: list[EvidenceItem] = Field(description="Local memory evidence used in the context.")
    gates: list[GateSummary] = Field(description="Verification gate summaries.")
    risk_level: RiskLevel = Field(description="Deterministic local risk level.")
    trust_decision: TrustDecision = Field(description="Planner trust outcome.")
    token_usage: dict[str, int] = Field(description="Token usage summary.")
    omitted_sources: list[str] = Field(description="Sources omitted with traceable reasons.")
    aicx: dict[str, Any] | None = Field(
        default=None,
        description="AICX bytecode compact dict for transport (lazy, no content inlined).",
    )
    aicx_delta: dict[str, Any] | None = Field(
        default=None,
        description="Cross-turn AICX delta vs the project's previous bytecode "
        "(omits unchanged evidence). Use instead of `aicx` when present.",
    )


class EvidenceRequest(BaseModel):
    """Planner request shared by runtime, CLI, API, workflow, and agent tools."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Natural-language context intent.")
    root: Path = Field(description="Project root used for local evidence lookup.")
    surface: RetrievalSurface = Field(description="Caller surface requesting evidence.")
    max_tokens: int = Field(gt=0, description="Maximum evidence token budget.")
    risk_level: str = Field(default="normal", description="Risk level for trust decisions.")
    refresh_policy: str = Field(default="default", description="Freshness policy for the request.")
    trace_parent: str | None = Field(default=None, description="Optional parent trace id.")
    expansion_rounds: int = Field(
        default=1,
        ge=0,
        le=10,
        description="Progressive graph-expansion rounds (0 disables expansion).",
    )
    graph_radius: int = Field(
        default=1,
        ge=0,
        le=10,
        description="Graph neighbor radius per expansion round.",
    )


class EvidenceItem(BaseModel):
    """Traceable evidence item emitted by the planner contract."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable evidence id.")
    content: str = Field(description="Evidence text or reversible handle payload.")
    source: str = Field(description="Human-readable source location.")
    source_type: str = Field(description="Source category.")
    provenance: dict[str, Any] = Field(description="Source provenance and retrieval metadata.")
    confidence: float = Field(ge=0.0, le=1.0, description="Normalized confidence score.")
    freshness: FreshnessStatus = Field(description="Verifiable evidence freshness.")
    surface: RetrievalSurface = Field(description="Surface that requested this evidence.")
    tokens: int = Field(ge=0, description="Estimated token count.")
    protected: bool = Field(default=False, description="Whether this evidence must be preserved.")
    classification: DataClassification = Field(
        default=DataClassification.INTERNAL,
        description="Security classification for the evidence.",
    )


class TrustDecision(BaseModel):
    """Planner trust outcome for the evidence plan."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="Trust status, such as sufficient or insufficient.")
    reason: str = Field(description="Human-readable deterministic reason.")


class EvidencePlan(BaseModel):
    """Complete evidence plan with trust, fallback, and trace metadata."""

    model_config = ConfigDict(extra="forbid")

    request: EvidenceRequest = Field(description="Original evidence request.")
    evidence: list[EvidenceItem] = Field(description="Ranked evidence items.")
    fallback_actions: list[str] = Field(description="Explicit fallback actions for consumers.")
    trust_decision: TrustDecision = Field(description="Overall trust decision.")
    trace_id: str = Field(description="Planner trace id.")
    omissions: list[str] = Field(default_factory=list, description="Omitted evidence reasons.")
    source_surfaces: list[RetrievalSurface] = Field(description="Surfaces represented in evidence.")


def evidence_trace_id(request: EvidenceRequest, evidence_ids: list[str]) -> str:
    """Build a deterministic trace id for an evidence request and ranked evidence."""

    digest = hashlib.sha256(
        "|".join([request.surface.value, request.query, str(request.root), *evidence_ids]).encode(
            "utf-8"
        )
    ).hexdigest()[:12]
    return f"evidence-plan-{digest}"
