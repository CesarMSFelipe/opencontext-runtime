"""Runtime events and the required category vocabulary (SPEC RC-004).

``RuntimeEvent`` mirrors ``02-runtime-architecture.md`` §16. Event ``type``
values are dotted strings whose prefix is one of the 16 required categories
(e.g. ``session.created``, ``workflow.started``, ``node.failed``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC, StrEnum


class EventCategory(StrEnum):
    """Required runtime event categories (book §16, 16 categories)."""

    session = "session"
    workflow = "workflow"
    node = "node"
    harness = "harness"
    policy = "policy"
    context = "context"
    memory = "memory"
    kg = "kg"
    skill = "skill"
    persona = "persona"
    provider = "provider"
    mutation = "mutation"
    inspection = "inspection"
    diagnosis = "diagnosis"
    escalation = "escalation"
    consolidation = "consolidation"


class RuntimeEvent(BaseModel):
    """A single append-only runtime event."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.runtime_event.v1"
    event_id: str = Field(default_factory=lambda: f"evt-{uuid4().hex[:12]}")
    session_id: str
    run_id: str | None = None
    workflow_id: str | None = None
    node_id: str | None = None
    type: str
    status: str
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(tz=UTC).isoformat())

    @property
    def category(self) -> str:
        """The category prefix of this event ``type`` (text before the first dot)."""
        return self.type.split(".", 1)[0]


def make_event(
    *,
    session_id: str,
    type: str,
    status: str,
    message: str = "",
    run_id: str | None = None,
    workflow_id: str | None = None,
    node_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeEvent:
    """Construct a :class:`RuntimeEvent` with a generated id and timestamp."""
    return RuntimeEvent(
        session_id=session_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id=node_id,
        type=type,
        status=status,
        message=message,
        metadata=metadata or {},
    )
