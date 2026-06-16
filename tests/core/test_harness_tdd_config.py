"""Config tests for harness.tdd_mode / strict_tdd (, task 3.8).

The harness TDD settings (``tdd_mode``/``strict_tdd``) must be readable from the
top-level OpenContext config so the runner can drive the TDD pre-gate from config
rather than from token ``budget_mode``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import (
    ConfigurationError,
    HarnessSettingsConfig,
    load_config,
    load_config_or_defaults,
)


def test_harness_section_defaults() -> None:
    cfg = load_config_or_defaults(None, auto_detect=False)
    assert cfg.harness.tdd_mode == "ask"
    assert cfg.harness.strict_tdd is False


def test_harness_settings_model_defaults() -> None:
    settings = HarnessSettingsConfig()
    assert settings.tdd_mode == "ask"
    assert settings.strict_tdd is False
    assert settings.approval_required_for_writes is False


def test_harness_tdd_mode_validation() -> None:
    HarnessSettingsConfig(tdd_mode="strict")
    HarnessSettingsConfig(tdd_mode="off")
    with pytest.raises(ValueError):
        HarnessSettingsConfig(tdd_mode="bogus")


def test_harness_section_loads_from_yaml(tmp_path: Path) -> None:
    config_yaml = tmp_path / "opencontext.yaml"
    config_yaml.write_text(
        "project:\n"
        "  name: demo\n"
        "harness:\n"
        "  tdd_mode: strict\n"
        "  strict_tdd: true\n"
        "  approval_required_for_writes: true\n",
        encoding="utf-8",
    )
    cfg = load_config(config_yaml)
    assert cfg.harness.tdd_mode == "strict"
    assert cfg.harness.strict_tdd is True
    assert cfg.harness.approval_required_for_writes is True


def test_harness_section_rejects_unknown_keys(tmp_path: Path) -> None:
    config_yaml = tmp_path / "opencontext.yaml"
    config_yaml.write_text(
        "project:\n  name: demo\nharness:\n  not_a_field: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError):
        load_config(config_yaml)
