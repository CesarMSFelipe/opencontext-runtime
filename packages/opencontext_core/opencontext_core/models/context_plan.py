"""ContextPlan model — the execution plan derived from a ContextContract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from opencontext_core.models.context_contract import VerificationGate

PlanMode = Literal["verified", "fast", "minimal"]
PlanTier = Literal["cheap", "precise", "critical"]
CompressionStrategy = Literal["none", "terse", "compact", "deep"]


class ContextPlan(BaseModel):
    """Execution plan for assembling a context pack for a classified task."""

    mode: PlanMode = Field(description="Retrieval mode: verified, fast, or minimal.")
    tier: PlanTier = Field(description="Budget tier driving strategy choices.")
    budget_tokens: int = Field(description="Maximum token budget for context assembly.")
    must_read: list[str] = Field(default_factory=list, description="Files that must be included.")
    should_read: list[str] = Field(
        default_factory=list, description="Files to include if budget allows."
    )
    must_verify: list[VerificationGate] = Field(default_factory=list)
    include_tests: bool = Field(default=False)
    include_memory: bool = Field(default=False)
    include_semantic: bool = Field(default=False)
    compression_strategy: CompressionStrategy = Field(default="terse")
    graph_radius: int = Field(default=1, ge=0)
    expansion_rounds: int = Field(default=1, ge=1)
    memory_query: str = Field(default="")
