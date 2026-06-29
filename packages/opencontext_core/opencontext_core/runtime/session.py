"""RuntimeSession, SessionStatus, LiveState, and ExecutionProfile.

Covers SPEC RC-002 (session model + 9-status enum), the ``LiveState``
projection (RC-006), and the convergence seam fields ``execution_profile`` and
``capability_snapshot`` (RC-CONV).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC, StrEnum


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class SessionStatus(StrEnum):
    """Session lifecycle statuses (book §7.3 eight + ``cancelled`` = 9)."""

    created = "created"
    running = "running"
    waiting_for_approval = "waiting_for_approval"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    escalated = "escalated"
    archived = "archived"
    cancelled = "cancelled"


class ExecutionProfile(BaseModel):
    """Convergence seam: the execution profile resolved at session start.

    A snapshot only — it records which profile governed the session. Behaviour
    selection (the Brain/Scheduler) is out of scope for PR-001.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.execution_profile.v1"
    name: str
    settings: dict[str, Any] = Field(default_factory=dict)


class RuntimeSession(BaseModel):
    """A first-class, persisted session (book §7.2)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.session.v1"
    session_id: str
    root: str
    task: str
    profile: str
    status: SessionStatus = SessionStatus.created
    active_run_id: str | None = None
    context_id: str | None = None
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    live_state_path: str = ""
    events_path: str = ""
    artifacts_root: str = ""

    # Convergence seams (RC-CONV).
    execution_profile: ExecutionProfile | None = None
    capability_snapshot: dict[str, bool] = Field(default_factory=dict)

    def touch(self) -> None:
        """Update the ``updated_at`` timestamp in place."""
        self.updated_at = _now_iso()


class LiveState(BaseModel):
    """The single-file projection of a session's current execution position."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    run_id: str | None = None
    workflow: str | None = None
    node: str | None = None
    status: str
    message: str = ""
    attempt: int = 0
    max_attempts: int = 0
    last_event_id: str | None = None
    updated_at: str = Field(default_factory=_now_iso)
