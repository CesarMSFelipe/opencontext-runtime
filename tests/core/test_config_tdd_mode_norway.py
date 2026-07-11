"""F1: an unquoted ``off`` in YAML must not crash config load / MCP startup.

YAML's "Norway problem": an unquoted ``off`` (and ``no``) parses as the Python
boolean ``False``. EVERY config field whose ``Literal`` includes ``"off"`` hits
this — ``tdd_mode`` and ``economy_mode`` on the flow config, ``tdd_mode`` on the
harness config, and ``mode`` on the openspec TDD section — so Pydantic rejects
the boolean ``False`` and the whole config load (and with it the MCP server
startup that loads config) fails with a ValidationError.

The fix is one shared ``coerce_yaml_off`` helper attached via
``field_validator(mode="before")`` on each such field: it coerces the boolean
``False`` back to the string ``"off"`` (the real Norway collision). Genuine
strings are left untouched and truly-unknown values still raise.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from opencontext_core.agentic.config import AgenticFlowConfig
from opencontext_core.compat import coerce_yaml_off
from opencontext_core.config import (
    HarnessSettingsConfig,
    default_config_data,
    load_config,
)
from opencontext_core.openspec.config import OpenSpecConfig, TDDSection

# (model, field) pairs whose Literal includes "off" and load from hand-authored YAML.
_OFF_LITERAL_FIELDS: tuple[tuple[type[BaseModel], str], ...] = (
    (HarnessSettingsConfig, "tdd_mode"),
    (AgenticFlowConfig, "tdd_mode"),
    (AgenticFlowConfig, "economy_mode"),
    (TDDSection, "mode"),
)


def test_harness_tdd_mode_bool_false_coerces_to_off() -> None:
    """``HarnessSettingsConfig`` accepts the YAML-boolean ``False`` as ``"off"``."""
    cfg = HarnessSettingsConfig.model_validate({"tdd_mode": False})
    assert cfg.tdd_mode == "off"


def test_agentic_flow_tdd_mode_bool_false_coerces_to_off() -> None:
    """``AgenticFlowConfig`` accepts the YAML-boolean ``False`` as ``"off"``."""
    cfg = AgenticFlowConfig.model_validate({"tdd_mode": False})
    assert cfg.tdd_mode == "off"


def test_string_tdd_modes_are_untouched() -> None:
    """The coercion only fires for the boolean collision; strings pass through."""
    for value in ("ask", "strict", "off"):
        assert HarnessSettingsConfig.model_validate({"tdd_mode": value}).tdd_mode == value
        assert AgenticFlowConfig.model_validate({"tdd_mode": value}).tdd_mode == value


def test_unknown_tdd_mode_still_rejected() -> None:
    """A genuinely-invalid value must still raise — the fix is narrow."""
    with pytest.raises(ValidationError):
        HarnessSettingsConfig.model_validate({"tdd_mode": "banana"})


def test_yaml_unquoted_off_loads_without_crash(tmp_path: Path) -> None:
    """The end-to-end symptom: an ``opencontext.yaml`` with unquoted ``off``
    (which yaml.safe_load turns into ``False``) loads cleanly instead of
    raising a ConfigurationError at MCP startup."""
    data = default_config_data()
    data.setdefault("harness", {})["tdd_mode"] = "off"
    text = yaml.safe_dump(data)
    # Force the unquoted-off shape a hand-authored file would carry.
    text = text.replace("tdd_mode: 'off'", "tdd_mode: off").replace(
        'tdd_mode: "off"', "tdd_mode: off"
    )
    # Sanity: this really parses to a Python bool (the Norway problem).
    assert yaml.safe_load(text)["harness"]["tdd_mode"] is False
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(text, encoding="utf-8")

    config = load_config(config_path)
    assert config.harness.tdd_mode == "off"


@pytest.mark.parametrize(("model", "field"), _OFF_LITERAL_FIELDS)
def test_every_off_literal_field_coerces_bool_false(model: type[BaseModel], field: str) -> None:
    """Every off-literal config field accepts the YAML-boolean ``False`` as ``"off"``."""
    cfg = model.model_validate({field: False})
    assert getattr(cfg, field) == "off"


def test_coerce_yaml_off_helper() -> None:
    """The shared helper only rewrites the boolean ``False``; everything else passes through."""
    assert coerce_yaml_off(False) == "off"
    for passthrough in ("off", "strict", "balanced", True, None, 0, ""):
        assert coerce_yaml_off(passthrough) is passthrough


def test_openspec_unquoted_off_loads_without_crash(tmp_path: Path) -> None:
    """openspec/config.yaml with an unquoted ``mode: off`` loads instead of raising."""
    text = "tdd:\n  mode: off\n"
    assert yaml.safe_load(text)["tdd"]["mode"] is False  # the Norway problem
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")

    config = OpenSpecConfig.load_optional(path)
    assert config is not None
    assert config.tdd.mode == "off"
