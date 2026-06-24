"""Preset factory — returns a fully-populated AgenticFlowConfig for named presets."""

from __future__ import annotations

from opencontext_core.agentic.config import (
    AgenticFlowConfig,
    BudgetMode,
    ComponentId,
    FlowMode,
    GitMode,
    MemoryMode,
    OpenSpecMode,
    PresetId,
)

# NOTE: Each preset activates a distinct set of components and modes.
_PRESETS: dict[PresetId, AgenticFlowConfig] = {
    PresetId.FULL: AgenticFlowConfig(
        preset=PresetId.FULL,
        components=[
            ComponentId.KG,
            ComponentId.COMPRESSION,
            ComponentId.MEMORY,
            ComponentId.CONDUCTOR,
            ComponentId.BUDGET,
            ComponentId.GIT,
            ComponentId.OPENSPEC,
        ],
        memory_mode=MemoryMode.ENGRAM,
        flow_mode=FlowMode.HYBRID,
        budget_mode=BudgetMode.STRICT,
        git_mode=GitMode.SINGLE_PR,
        openspec_mode=OpenSpecMode.FULL,
        total_budget=40000,
        phase_budget=8000,
        tdd_mode="ask",
        approval_before_apply=True,
        install_engram_if_missing=True,
        allow_automatic_archive=False,
        allow_background_indexing=True,
    ),
    PresetId.AGENTIC_MINIMAL: AgenticFlowConfig(
        preset=PresetId.AGENTIC_MINIMAL,
        components=[ComponentId.CONDUCTOR, ComponentId.BUDGET],
        memory_mode=MemoryMode.LOCAL,
        flow_mode=FlowMode.AUTOMATIC,
        budget_mode=BudgetMode.WARN,
        git_mode=GitMode.NONE,
        openspec_mode=OpenSpecMode.MINIMAL,
        total_budget=20000,
        phase_budget=4000,
        tdd_mode="off",
        approval_before_apply=False,
        install_engram_if_missing=False,
        allow_automatic_archive=True,
        allow_background_indexing=False,
    ),
    PresetId.MEMORY_ONLY: AgenticFlowConfig(
        preset=PresetId.MEMORY_ONLY,
        components=[ComponentId.MEMORY],
        memory_mode=MemoryMode.ENGRAM,
        flow_mode=FlowMode.OBSERVE_ONLY,
        budget_mode=BudgetMode.OFF,
        git_mode=GitMode.NONE,
        openspec_mode=OpenSpecMode.OFF,
        total_budget=None,
        phase_budget=None,
        tdd_mode="off",
        approval_before_apply=False,
        install_engram_if_missing=True,
        allow_automatic_archive=False,
        allow_background_indexing=False,
    ),
    PresetId.SDD_ONLY: AgenticFlowConfig(
        preset=PresetId.SDD_ONLY,
        components=[ComponentId.CONDUCTOR, ComponentId.OPENSPEC],
        memory_mode=MemoryMode.LOCAL,
        flow_mode=FlowMode.STEPWISE,
        budget_mode=BudgetMode.WARN,
        git_mode=GitMode.SINGLE_PR,
        openspec_mode=OpenSpecMode.FULL,
        total_budget=40000,
        phase_budget=8000,
        tdd_mode="strict",
        approval_before_apply=True,
        install_engram_if_missing=False,
        allow_automatic_archive=False,
        allow_background_indexing=True,
    ),
    PresetId.CONTEXT_ONLY: AgenticFlowConfig(
        preset=PresetId.CONTEXT_ONLY,
        components=[ComponentId.KG, ComponentId.COMPRESSION],
        memory_mode=MemoryMode.OFF,
        flow_mode=FlowMode.OBSERVE_ONLY,
        budget_mode=BudgetMode.WARN,
        git_mode=GitMode.NONE,
        openspec_mode=OpenSpecMode.OFF,
        total_budget=None,
        phase_budget=None,
        tdd_mode="off",
        approval_before_apply=False,
        install_engram_if_missing=False,
        allow_automatic_archive=False,
        allow_background_indexing=True,
    ),
    PresetId.CUSTOM: AgenticFlowConfig(
        preset=PresetId.CUSTOM,
        components=[],
    ),
}


def preset_config(preset: PresetId) -> AgenticFlowConfig:
    """Return the AgenticFlowConfig for the given preset."""
    return _PRESETS[preset]


if __name__ == "__main__":
    for pid in PresetId:
        cfg = preset_config(pid)
        assert cfg.preset == pid, f"preset field mismatch for {pid}"
        # Validate by round-tripping through model_validate
        AgenticFlowConfig.model_validate(cfg.model_dump())

    custom = preset_config(PresetId.CUSTOM)
    assert custom.components == [], "CUSTOM preset must have empty components"

    full = preset_config(PresetId.FULL)
    assert full.install_engram_if_missing is True

    print("agentic/presets.py self-check passed.")
