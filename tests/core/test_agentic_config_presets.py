"""Tests for AgenticFlowConfig and preset_config factory — spec §Domain 1."""

from __future__ import annotations

import pydantic
import pytest

from opencontext_core.agentic.config import AgenticFlowConfig, ComponentId, PresetId
from opencontext_core.agentic.presets import preset_config


def test_valid_config_round_trips() -> None:
    cfg = AgenticFlowConfig(
        preset=PresetId.FULL,
        components=[ComponentId.KG, ComponentId.MEMORY],
        total_budget=10000,
    )
    dumped = cfg.model_dump()
    restored = AgenticFlowConfig.model_validate(dumped)
    assert restored.preset == PresetId.FULL
    assert ComponentId.KG in restored.components
    assert restored.total_budget == 10000


def test_unknown_field_rejected() -> None:
    with pytest.raises(pydantic.ValidationError):
        AgenticFlowConfig(unknown_extra_field="bad")  # type: ignore[call-arg]


def test_all_six_presets_return_valid_config() -> None:
    for preset in PresetId:
        cfg = preset_config(preset)
        assert isinstance(cfg, AgenticFlowConfig)
        assert cfg.preset == preset
        # Validate via round-trip
        AgenticFlowConfig.model_validate(cfg.model_dump())


def test_full_preset_has_install_engram_true() -> None:
    cfg = preset_config(PresetId.FULL)
    assert cfg.install_engram_if_missing is True


def test_custom_preset_has_empty_components() -> None:
    cfg = preset_config(PresetId.CUSTOM)
    assert cfg.components == []


def test_config_json_round_trip() -> None:
    cfg = preset_config(PresetId.SDD_ONLY)
    json_str = cfg.model_dump_json()
    restored = AgenticFlowConfig.model_validate_json(json_str)
    assert restored.preset == PresetId.SDD_ONLY
    assert restored.tdd_mode == "strict"


def test_oc_new_run_state_accepts_config_field() -> None:
    """OcNewRunState.config field survives model_dump / model_validate round-trip."""
    from opencontext_core.oc_new.models import ChangeIdentity, OcNewRunState, PhaseState

    identity = ChangeIdentity.from_task("test task")
    state = OcNewRunState(
        identity=identity,
        task="test task",
        phases=[PhaseState(name="explore")],
        config=preset_config(PresetId.AGENTIC_MINIMAL),
    )
    dumped = state.model_dump()
    restored = OcNewRunState.model_validate(dumped)
    assert restored.config is not None
    assert restored.config.preset == PresetId.AGENTIC_MINIMAL
