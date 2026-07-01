"""SkillBundle — the v2 skill manifest (CONV2 / commit 011)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SkillTier(StrEnum):
    """Explicit tier semantics: tier0 is built-in, tier3 is experimental."""

    tier0 = "tier0"
    tier1 = "tier1"
    tier2 = "tier2"
    tier3 = "tier3"


class SkillBundle(BaseModel):
    """A complete skill manifest for the v2 ecosystem.

    The bundle is the unit of registration: audit checks tier + persona_compat
    + contract, gates must all pass, and the token_budget constrains runtime.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    tier: SkillTier
    profile: str = "balanced"
    task: str
    workflow_id: str
    persona: str
    gates: list[str] = Field(default_factory=list)
    token_budget: int = 0
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)


__all__ = ["SkillBundle", "SkillTier"]
