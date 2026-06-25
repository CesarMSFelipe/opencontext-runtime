"""Data models for the oc-new stateful conductor."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.agentic.config import AgenticFlowConfig
from opencontext_core.compat import UTC

PhaseName = Literal[
    "explore",
    "propose",
    "spec",
    "design",
    "tasks",
    "approval",
    "apply",
    "verify",
    "review",
    "archive",
]

PhaseStatus = Literal[
    "pending",
    "running",
    "passed",
    "warning",
    "failed",
    "blocked",
    "skipped",
]

NextActionKind = Literal[
    "spawn_subagent",
    "request_approval",
    "wait_for_artifact",
    "resume",
    "archive",
    "done",
    "blocked",
    "observe_only",
]

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class ChangeIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_id: str
    run_id: str
    trace_id: str
    memory_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    @classmethod
    def from_task(cls, task: str) -> ChangeIdentity:
        slug = _SLUG_RE.sub("-", task.strip().lower()).strip("-")[:80]
        if not slug:
            slug = f"change-{uuid4().hex[:8]}"
        return cls(
            change_id=slug,
            run_id=f"ocnew-{uuid4().hex[:12]}",
            trace_id=f"trace-{uuid4().hex[:12]}",
            memory_key=f"change:{slug}",
        )


class PhaseDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: PhaseName
    persona: str | None
    skill: str | None
    writes_code: bool = False
    requires_approval: bool = False
    required_artifacts: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)


class PhaseState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: PhaseName
    status: PhaseStatus = "pending"
    artifact_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class NextAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: NextActionKind
    phase: PhaseName | None = None
    persona: str | None = None
    instruction: str
    required_tools: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    # NOTE: metadata carries transport data (memory policy, budget hints) keyed by subsystem.
    metadata: dict = Field(default_factory=dict)


class OcNewRunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.oc_new_state.v1"
    identity: ChangeIdentity
    task: str
    phases: list[PhaseState]
    current_phase: PhaseName | None = None
    next_action: NextAction | None = None
    blocked_reason: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    # NOTE: config is persisted so resume() is faithful to the original preset.
    config: AgenticFlowConfig | None = None

    def phase(self, name: PhaseName) -> PhaseState:
        for p in self.phases:
            if p.name == name:
                return p
        raise KeyError(name)

    def completed_phases(self) -> list[PhaseName]:
        return [p.name for p in self.phases if p.status in {"passed", "warning", "skipped"}]


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    path: str | None = None
    kind: str = ""


class HandoffBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_budget: int = 0
    used_before_phase: int = 0
    max_output_tokens: int = 0
    budget_mode: str = "warn"


class AgentHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.agent_handoff.v2"
    run_id: str
    change_id: str
    trace_id: str
    phase: PhaseName
    persona: str
    task: str
    memory_key: str
    required_inputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    context_summary: str = ""
    previous_phase_summary: str = ""
    memory_backend: str = "local"
    read_memory_layers: list[str] = Field(default_factory=list)
    write_memory_layers: list[str] = Field(default_factory=list)
    # v2 fields (all defaulted for backwards compat)
    skill: str = ""
    skill_path: str | None = None
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    budget: HandoffBudget = Field(default_factory=HandoffBudget)
    context_report_ref: str | None = None
    result_schema: str = "opencontext.phase_result.v1"
    denied_tools: list[str] = Field(default_factory=list)


def render_handoff_markdown(handoff: AgentHandoff) -> str:
    def _items(lst: list[str]) -> str:
        return "\n".join(f"- `{x}`" for x in lst) if lst else "- none"

    return f"""# OpenContext Agent Handoff

Run: `{handoff.run_id}`
Change: `{handoff.change_id}`
Trace: `{handoff.trace_id}`
Phase: `{handoff.phase}`
Persona: `{handoff.persona}`

## Task

{handoff.task}

## Memory

Use memory key: `{handoff.memory_key}`

## Required inputs

{_items(handoff.required_inputs)}

## Expected outputs

{_items(handoff.expected_outputs)}

## Allowed tools

{_items(handoff.allowed_tools)}

## Context summary

{handoff.context_summary or "No context summary available."}

## Previous phase summary

{handoff.previous_phase_summary or "No previous phase summary available."}
"""
