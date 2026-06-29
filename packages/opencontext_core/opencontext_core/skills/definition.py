"""SkillDefinition — contract-bearing skill schema (PR-006, Skill Contract v1).

The legacy ``SkillEntry``/``SkillEntryV2`` (``skills/registry.py``) are *discovery*
records scanned from SKILL.md files. A ``SkillDefinition`` is the *contract*: a
loadable procedure with typed inputs/outputs, required harnesses/capabilities, a
tier, a category, and a token budget (book doc 06). The two coexist — the scanner
stays load-bearing for editor skill discovery; this model is additive.

Layer L6: imports only L0 (compat) + the L6 base.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.registries.base import RegistryMetadata

# Skill Contract v1 (doc 59 — internal contract versioning).
SKILL_CONTRACT_VERSION = 1
SKILL_SCHEMA_VERSION = "opencontext.skill.v1"

# Skill tiers (REG-CONV): T0 always-on, T1 per-phase, T2 conditional.
SkillTier = Literal["T0", "T1", "T2"]


class SkillDefinition(BaseModel):
    """A registry-driven skill contract (book doc 06 — Skill Definition)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=SKILL_SCHEMA_VERSION)
    id: str = Field(description="Skill id (slug), e.g. 'oc-apply-surgical'. Registry key.")
    name: str = ""
    version: str = "1.0"
    tier: SkillTier = Field(description="T0 always-on | T1 per-phase | T2 conditional.")
    category: str = Field(
        description="Context|Planning|Mutation|Inspection|Diagnosis|Review|Consolidation."
    )

    workflow_nodes: list[str] = Field(
        default_factory=list, description="Workflow nodes that trigger this skill."
    )
    triggers: list[str] = Field(default_factory=list, description="Free-form trigger keywords.")

    inputs: list[str] = Field(default_factory=list, description="Declared typed inputs.")
    outputs: list[str] = Field(default_factory=list, description="Declared typed outputs.")
    required_harnesses: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    token_budget: int = 0
    failure_modes: list[str] = Field(default_factory=list)

    owner: str = ""
    maturity: str = Field(default="stable", description="experimental|beta|stable.")

    # Forward-compat seam: per-skill success/cost/latency metrics are populated in
    # PR-017 (benchmarking). Declared here as the field so the contract is stable;
    # population + policy auto-disable are DEFERRED (spec AC-SK5 / REG-CONV).
    benchmark_metadata: dict[str, Any] | None = None

    metadata: RegistryMetadata = Field(default_factory=RegistryMetadata)

    def missing_inputs(self, provided: dict[str, Any] | set[str] | list[str]) -> list[str]:
        """Return declared inputs absent from ``provided`` (validate-inputs step)."""
        if isinstance(provided, dict):
            present = set(provided.keys())
        else:
            present = set(provided)
        return [name for name in self.inputs if name not in present]

    def missing_outputs(self, produced: dict[str, Any] | set[str] | list[str]) -> list[str]:
        """Return declared outputs absent from ``produced`` (validate-output step)."""
        if isinstance(produced, dict):
            present = set(produced.keys())
        else:
            present = set(produced)
        return [name for name in self.outputs if name not in present]
