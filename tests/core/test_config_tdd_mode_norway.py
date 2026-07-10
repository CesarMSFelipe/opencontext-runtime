"""F1: unquoted ``tdd_mode: off`` must not crash config load / MCP startup.

YAML's "Norway problem": an unquoted ``off`` (and ``no``) parses as the Python
boolean ``False``. ``tdd_mode`` is a ``Literal["ask", "strict", "off"]`` on both
``HarnessSettingsConfig`` (config.py) and ``AgenticFlowConfig`` (agentic/config.py),
so Pydantic rejects the boolean ``False`` and the whole config load — and with it
the MCP server startup that loads config — fails with a ValidationError.

The fix is a ``field_validator(mode="before")`` that coerces the boolean ``False``
back to the string ``"off"`` (the real Norway collision). Genuine strings are left
untouched and truly-unknown values still raise.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from opencontext_core.agentic.config import AgenticFlowConfig
from opencontext_core.config import (
    HarnessSettingsConfig,
    default_config_data,
    load_config,
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
