"""AgenticFlowConfig — preset-driven configuration for the oc-new agentic flow."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from opencontext_core.compat import StrEnum, coerce_yaml_off


class ComponentId(StrEnum):
    """Identifiable components of the agentic stack."""

    KG = "kg"
    COMPRESSION = "compression"
    MEMORY = "memory"
    CONDUCTOR = "conductor"
    BUDGET = "budget"
    GIT = "git"
    OPENSPEC = "openspec"
    ENGRAM = "engram"
    SDD = "sdd"
    MCP = "mcp"
    SKILLS = "skills"
    PERSONAS = "personas"
    RECEIPTS = "receipts"
    AICX = "aicx"
    TUI = "tui"


class PresetId(StrEnum):
    """Named configuration presets."""

    FULL = "full-opencontext"
    AGENTIC_MINIMAL = "agentic-minimal"
    AGENTIC_SAFE = "agentic-safe"
    MEMORY_ONLY = "memory-only"
    SDD_ONLY = "sdd-only"
    CONTEXT_ONLY = "context-only"
    CUSTOM = "custom"


class MemoryMode(StrEnum):
    """How the agentic flow reads and writes memory."""

    AUTO = "auto"
    ENGRAM = "engram"
    LOCAL = "local"
    OFF = "off"
    HYBRID = "hybrid"
    ENGRAM_ONLY = "engram_only"


class FlowMode(StrEnum):
    """Pause and execution policy for the agentic flow."""

    AUTOMATIC = "automatic"
    STEPWISE = "stepwise"
    HYBRID = "hybrid"
    ENGRAM_ONLY = "engram_only"
    OPENSPEC_ONLY = "openspec_only"
    OBSERVE_ONLY = "observe_only"


class BudgetMode(StrEnum):
    """Token budget enforcement strategy."""

    STRICT = "strict"
    WARN = "warn"
    OFF = "off"
    ADAPTIVE = "adaptive"
    ASK = "ask"


class GitMode(StrEnum):
    """Git workflow strategy for generated work units."""

    NONE = "none"
    SINGLE_PR = "single_pr"
    STACKED_PRS = "stacked_prs"
    LOCAL_BRANCH = "local_branch"
    COMMIT_ONLY = "commit_only"
    PER_TASK_PRS = "per_task_prs"


class OpenSpecMode(StrEnum):
    """How the flow persists artifacts to OpenSpec."""

    FULL = "full"
    MINIMAL = "minimal"
    OFF = "off"


class AgenticFlowConfig(BaseModel, extra="forbid"):
    """Unified configuration for the OcNewConductor agentic flow."""

    preset: PresetId = PresetId.CUSTOM
    components: list[ComponentId] = Field(default_factory=list)
    memory_mode: MemoryMode = MemoryMode.AUTO
    flow_mode: FlowMode = FlowMode.AUTOMATIC
    budget_mode: BudgetMode = BudgetMode.WARN
    git_mode: GitMode = GitMode.NONE
    openspec_mode: OpenSpecMode = OpenSpecMode.OFF

    total_budget: int | None = 40000
    phase_budget: int | None = 8000
    tdd_mode: Literal["strict", "ask", "off"] = "ask"
    approval_before_apply: bool = True

    @field_validator("tdd_mode", "economy_mode", mode="before")
    @classmethod
    def _coerce_yaml_off(cls, value: Any) -> Any:
        # YAML "Norway problem": unquoted ``off`` parses as the boolean ``False``
        # before validation. Both these Literals include "off"; coerce so a
        # hand-authored ``tdd_mode: off`` / ``economy_mode: off`` does not crash
        # flow config load. Strings pass through; unknown values still fail.
        return coerce_yaml_off(value)

    install_engram_if_missing: bool = True
    allow_automatic_archive: bool = False
    allow_background_indexing: bool = True
    economy_mode: Literal["off", "balanced", "aggressive"] = "balanced"
    compact_handoffs: bool = True
    max_handoff_tokens: int = 1200
    setup_engram_for_agent: bool = True
    approval_before_git: bool = True


if __name__ == "__main__":
    # Self-check: round-trip validation
    cfg = AgenticFlowConfig(preset=PresetId.FULL, components=[ComponentId.KG, ComponentId.MEMORY])
    dumped = cfg.model_dump()
    restored = AgenticFlowConfig.model_validate(dumped)
    assert restored.preset == PresetId.FULL
    assert ComponentId.KG in restored.components

    import pydantic

    try:
        AgenticFlowConfig(unknown_field="bad")  # type: ignore[call-arg]
        raise AssertionError("Expected ValidationError for unknown field")
    except pydantic.ValidationError:
        pass

    print("agentic/config.py self-check passed.")
