"""Execution profile & strategy contracts (CP-007, CP-010).

An ``ExecutionProfile`` binds the four runtime levers — token budget, retry/
diagnosis attempts, harness strictness, and provider routing — into one named
unit, so selecting a profile configures all four coherently. An
``ExecutionProfileStrategy`` is a named intent (``fast``/``cheap``/...) that maps
onto a profile.

This is deliberately DISTINCT from the per-phase *model* profile
(``sdd_model_profile`` ∈ default/cheap/hybrid/premium, which assigns an LLM to
each SDD phase) and from install-time setup presets (``setup/presets.py``). A
model profile picks *which model*; an execution profile picks *how hard to try*.

Layering (doc 58): L3. Imports only ``pydantic`` and ``compat`` (L0).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum

EXECUTION_PROFILE_SCHEMA_VERSION = "opencontext.execution_profile.v1"
EXECUTION_STRATEGY_SCHEMA_VERSION = "opencontext.execution_strategy.v1"

# Provider routing posture a profile requests. The resolver reconciles this with
# the live capability graph (e.g. local_first falls back when no local provider).
ProviderRouting = Literal["local_first", "remote_first", "policy"]


class HarnessStrictness(StrEnum):
    """How blocking the verification harness is for a profile."""

    advisory = "advisory"  # gates report, never block
    warn = "warn"  # gates warn loudly, do not block
    strict = "strict"  # gates block on failure


class ExecutionProfile(BaseModel):
    """A named runtime posture binding budget/retries/strictness/routing (CP-010)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = EXECUTION_PROFILE_SCHEMA_VERSION
    id: str = Field(description="Profile id, e.g. 'balanced'.")
    token_budget: int = Field(gt=0, description="Per-phase context token budget.")
    max_retries: int = Field(
        ge=0, description="Diagnosis/retry attempts before giving up on a step."
    )
    harness_strictness: HarnessStrictness = Field(description="How blocking the harness is.")
    provider_routing: ProviderRouting = Field(description="Preferred provider routing posture.")
    description: str = Field(default="", description="Human-readable summary.")


class ExecutionProfileStrategy(BaseModel):
    """A named execution intent that maps onto an ``ExecutionProfile`` (CP-009)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = EXECUTION_STRATEGY_SCHEMA_VERSION
    id: str = Field(description="Strategy id, e.g. 'fast'.")
    profile_id: str = Field(description="The ExecutionProfile id this strategy resolves to.")
    description: str = Field(default="", description="Human-readable summary.")
