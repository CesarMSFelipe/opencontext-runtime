"""load_config rejects a non-enum security.mode and unknown keys.

RED first: ``load_config`` must raise ``ConfigurationError`` for an invalid
``security.mode`` and for unknown config keys (``extra="forbid"``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from opencontext_core.config import SecurityMode, default_config_data, load_config
from opencontext_core.errors import ConfigurationError


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "opencontext.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_load_config_rejects_non_enum_security_mode(tmp_path: Path) -> None:
    data = default_config_data()
    data["security"]["mode"] = "cross_project"  # not a SecurityMode member
    path = _write(tmp_path, data)

    with pytest.raises(ConfigurationError):
        load_config(path)


def test_load_config_rejects_open_security_mode(tmp_path: Path) -> None:
    data = default_config_data()
    data["security"]["mode"] = "open"
    path = _write(tmp_path, data)

    with pytest.raises(ConfigurationError):
        load_config(path)


def test_load_config_rejects_hyphenated_air_gapped(tmp_path: Path) -> None:
    data = default_config_data()
    data["security"]["mode"] = "air-gapped"  # hyphen, not air_gapped
    path = _write(tmp_path, data)

    with pytest.raises(ConfigurationError):
        load_config(path)


def test_load_config_rejects_unknown_security_key(tmp_path: Path) -> None:
    data = default_config_data()
    data["security"]["bogus_key"] = True
    path = _write(tmp_path, data)

    with pytest.raises(ConfigurationError):
        load_config(path)


def test_load_config_accepts_every_valid_mode(tmp_path: Path) -> None:
    for mode in SecurityMode:
        data = default_config_data()
        data["security"]["mode"] = mode.value
        path = tmp_path / f"{mode.value}.yaml"
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        config = load_config(path)
        assert config.security.mode == mode
