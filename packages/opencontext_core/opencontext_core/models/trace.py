"""Trace models for observability and auditability."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.models.context import ContextItem, PromptSection, TokenBudget

# --- KG event names (PR-008, OC-KG-001 §21; family "kg" per doc 59) -----------
KG_EVENT_FAMILY = "kg"

KG_INDEX_STARTED = "kg.index.started"
KG_INDEX_COMPLETED = "kg.index.completed"
KG_INDEX_FAILED = "kg.index.failed"
KG_QUERY_STARTED = "kg.query.started"
KG_QUERY_COMPLETED = "kg.query.completed"
KG_SUBGRAPH_CREATED = "kg.subgraph.created"
KG_DELTA_CREATED = "kg.delta.created"
KG_NODE_SUPERSEDED = "kg.node.superseded"
KG_CONFIDENCE_LOW = "kg.confidence.low"

# The complete set of required KG events (guard/test surface).
KG_EVENTS: frozenset[str] = frozenset(
    {
        KG_INDEX_STARTED,
        KG_INDEX_COMPLETED,
        KG_INDEX_FAILED,
        KG_QUERY_STARTED,
        KG_QUERY_COMPLETED,
        KG_SUBGRAPH_CREATED,
        KG_DELTA_CREATED,
        KG_NODE_SUPERSEDED,
        KG_CONFIDENCE_LOW,
    }
)


class RunEvent(BaseModel):
    """One immutable typed step in a run's deterministic event ledger.

    Each event pairs an action (what the run set out to do for a phase) with its
    observation (what happened). Events are append-only and ordered by ``index``
    so a completed run can be inspected or replayed step by step. The model is
    frozen: once appended, an event never changes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int = Field(description="Zero-based position of this event in the run ledger.")
    phase: str = Field(description="Phase id this event belongs to (e.g. 'apply').")
    action: str = Field(description="Action kind performed for the phase (e.g. 'run_phase').")
    inputs_summary: str = Field(
        default="",
        description="Short, deterministic summary of the action's inputs.",
    )
    status: str = Field(description="Outcome status (passed/warning/failed/skipped).")
    observation: str = Field(
        default="",
        description="What was observed after the action ran.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="UTC timestamp when the event was recorded.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured detail for replay/inspection.",
    )


class TraceEvent(BaseModel):
    """OpenTelemetry-compatible span event."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Event name.")
    timestamp: datetime = Field(description="Event timestamp.")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Event attributes.")


class TraceSpan(BaseModel):
    """OpenTelemetry-compatible span model without requiring an OTel dependency."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(description="Trace identifier shared by related spans.")
    span_id: str = Field(description="Unique span identifier.")
    parent_span_id: str | None = Field(default=None, description="Parent span id.")
    name: str = Field(description="Span name.")
    start_time: datetime = Field(description="Span start timestamp.")
    end_time: datetime | None = Field(default=None, description="Span end timestamp.")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Span attributes.")
    events: list[TraceEvent] = Field(default_factory=list, description="Span events.")


class RuntimeTrace(BaseModel):
    """Complete trace for one runtime workflow execution."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Unique run identifier.")
    trace_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="OpenTelemetry-compatible trace id.",
    )
    span_id: str = Field(
        default_factory=lambda: uuid4().hex[:16],
        description="Root span id.",
    )
    parent_span_id: str | None = Field(default=None, description="Root parent span id.")
    name: str = Field(default="workflow.run", description="Root span name.")
    start_time: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="Root span start time.",
    )
    end_time: datetime | None = Field(default=None, description="Root span end time.")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Root span attributes.")
    events: list[TraceEvent] = Field(default_factory=list, description="Root span events.")
    spans: list[TraceSpan] = Field(default_factory=list, description="Nested trace spans.")
    workflow_name: str = Field(description="Workflow that was executed.")
    input: str = Field(description="Original user request.")
    provider: str = Field(description="Selected LLM provider.")
    model: str = Field(description="Selected LLM model.")
    selected_context_items: list[ContextItem] = Field(
        description="Context items included in the prompt.",
    )
    discarded_context_items: list[ContextItem] = Field(
        description="Candidate context items excluded from the prompt.",
    )
    token_budget: TokenBudget = Field(description="Calculated token budget.")
    token_estimates: dict[str, int] = Field(description="Before and after token estimates.")
    compression_strategy: str = Field(description="Configured compression strategy.")
    prompt_sections: list[PromptSection] = Field(description="Assembled prompt sections.")
    final_answer: str = Field(description="Final LLM answer.")
    timings_ms: dict[str, float] = Field(
        default_factory=dict,
        description="Step durations in milliseconds.",
    )
    errors: list[str] = Field(default_factory=list, description="Errors captured during the run.")
    created_at: datetime = Field(description="UTC trace creation timestamp.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional trace metadata.",
    )
    event_ledger: list[RunEvent] = Field(
        default_factory=list,
        description="Append-only typed action/observation events for deterministic replay.",
    )
