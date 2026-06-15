"""Memory models for future local and external memory stores."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum
from opencontext_core.models.context import DataClassification
from opencontext_core.models.project import ProjectManifest


class MemoryType(StrEnum):
    """Supported memory record categories."""

    PROJECT = "project"
    FILE = "file"
    SYMBOL = "symbol"
    STRUCTURED_FACT = "structured_fact"
    DECISION = "decision"
    OBSERVATION = "observation"
    PREFERENCE = "preference"
    MILESTONE = "milestone"
    DISCOVERY = "discovery"
    ADVICE = "advice"


class MemoryItem(BaseModel):
    """A typed memory record that can be persisted or retrieved.

    Based on a hierarchical drawer structure, with support for
    hierarchical organization (wing/room) and priority-based
    retrieval.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable memory identifier.")
    memory_type: MemoryType = Field(description="Memory category.")
    content: str = Field(description="Memory payload (verbatim).")
    source: str = Field(description="Origin of the memory record.")
    created_at: datetime = Field(description="Creation timestamp.")
    classification: DataClassification = Field(
        default=DataClassification.INTERNAL,
        description="Data classification for security policy.",
    )
    priority: int = Field(
        default=1,
        description="Priority 0 (highest) to 3 (lowest).",
        ge=0,
        le=3,
    )
    trusted: bool = Field(
        default=False,
        description="Whether this memory is from a trusted source.",
    )
    redacted: bool = Field(
        default=False,
        description="Whether content has been redacted.",
    )
    tokens: int | None = Field(
        default=None,
        description="Cached token count for this item.",
        ge=0,
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional memory metadata.",
    )


class ProjectMemorySnapshot(BaseModel):
    """A project memory snapshot combining manifest, facts, and decisions."""

    model_config = ConfigDict(extra="forbid")

    manifest: ProjectManifest = Field(description="Indexed project manifest.")
    facts: list[MemoryItem] = Field(default_factory=list, description="Structured facts.")
    decisions: list[MemoryItem] = Field(default_factory=list, description="Decision memories.")
    observations: list[MemoryItem] = Field(
        default_factory=list, description="Session observations."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional snapshot metadata.",
    )
