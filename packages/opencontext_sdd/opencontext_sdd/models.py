"""Typed models used by the status resolver and dispatcher.

These are intentionally small Pydantic v2 models — separate from the main
``Status`` model so callers can type-hint just the slice they need.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ArtifactState = Literal["missing", "partial", "done"]


class PhaseRef(BaseModel):
    """Reference to a single SDD phase with its current state."""

    model_config = ConfigDict(extra="forbid")

    name: Literal["explore", "propose", "spec", "design", "tasks", "apply", "verify", "archive"]
    state: ArtifactState = "missing"
    path: str | None = None


class BlockReasons(BaseModel):
    """Machine-readable what/why/next for a blocked status (UVD-009)."""

    model_config = ConfigDict(extra="forbid")

    reasons: list[str] = Field(default_factory=list)
    next_step: str = "select-change"


class SourceDirEntry(BaseModel):
    """One source directory in the skill-registry discovery list (used by PR1.c)."""

    model_config = ConfigDict(extra="forbid")

    path: str
    scope: Literal["user", "project", "shared"] = "project"
    priority: int = 0
