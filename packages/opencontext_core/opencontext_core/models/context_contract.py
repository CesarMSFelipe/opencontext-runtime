"""ContextContract and VerificationGate models for OpenContext Runtime v2."""

from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, Field

from opencontext_core.models.evidence import EvidenceRef

RiskTier = Literal["cheap", "precise", "critical"]


class VerificationGate(BaseModel):
    """A gate that must pass before a context contract is considered verified."""

    id: str = Field(description="Unique gate identifier, e.g. 'run-tests'.")
    required: bool = Field(default=True, description="Whether this gate is mandatory.")
    passed: bool | None = Field(default=None, description="None = not yet evaluated.")


class ContextContract(BaseModel):
    """Declarative contract describing what context a task requires and how to verify it."""

    task: str = Field(description="Free-text task description.")
    task_type: str = Field(description="Classified task type (bugfix, feature, etc).")
    risk_level: str = Field(description="Risk level: low, medium, high.")
    risk_tier: RiskTier = Field(description="Budget tier: cheap, precise, or critical.")
    language: str | None = Field(default=None)
    framework: str | None = Field(default=None)
    known: list[EvidenceRef] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    required_symbols: list[str] = Field(default_factory=list)
    required_files: list[str] = Field(default_factory=list)
    required_memories: list[str] = Field(default_factory=list)
    must_verify: list[VerificationGate] = Field(default_factory=list)
    forbidden_sources: list[str] = Field(default_factory=list)
    token_budget: int = Field(description="Maximum token budget for context assembly.")

    def is_complete(self) -> bool:
        """Return True only when required symbols/files AND must_verify are both non-empty."""
        has_sources = bool(self.required_symbols or self.required_files)
        has_gates = bool(self.must_verify)
        return has_sources and has_gates

    def to_yaml(self) -> str:
        """Serialize to human-readable YAML."""
        data = self.model_dump()
        # model_dump() already recursed nested models into dicts, so yaml.dump won't choke.
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
