"""Agent signal primitives for cross-agent coordination."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from opencontext_core.compat import StrEnum


class AgentSignalKind(StrEnum):
    """Kind of signal an agent can emit."""

    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    HEARTBEAT = "heartbeat"


@dataclass
class AgentSignal:
    """An append-only signal record emitted by an agent."""

    signal_id: str
    lease_id: str
    kind: AgentSignalKind
    created_at: datetime = field(default_factory=lambda: datetime.now())
    payload: str | None = None
