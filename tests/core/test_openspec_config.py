"""OpenSpecConfig — governance model for openspec/config.yaml.

`extra='forbid'` means a stray top-level key raises ``ValidationError``
naming the unknown key. Missing files are tolerated via ``load_optional``
which returns ``None`` instead of raising.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from opencontext_core.openspec.config import OpenSpecConfig


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "openspec" / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_load_optional_returns_none_when_missing(tmp_path: Path) -> None:
    missing = tmp_path / "openspec" / "config.yaml"
    assert OpenSpecConfig.load_optional(missing) is None


def test_load_optional_loads_well_formed_config(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        {
            "tdd": {"mode": "strict"},
            "quality_gates": {"requirements": True, "tasks": True},
        },
    )
    cfg = OpenSpecConfig.load_optional(path)
    assert cfg is not None
    assert cfg.tdd.mode == "strict"
    assert cfg.quality_gates.requirements is True
    assert cfg.quality_gates.tasks is True


def test_load_optional_raises_validation_error_for_unknown_key(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        {
            "tdd": {"mode": "strict"},
            "definitely_not_a_real_key": 42,
        },
    )
    with pytest.raises(ValidationError) as excinfo:
        OpenSpecConfig.load_optional(path)
    assert "definitely_not_a_real_key" in str(excinfo.value)


def test_load_optional_defaults_when_minimal(tmp_path: Path) -> None:
    """A bare ``{}`` config still loads with sensible defaults."""
    path = _write_yaml(tmp_path, {})
    cfg = OpenSpecConfig.load_optional(path)
    assert cfg is not None
    assert cfg.tdd.mode == "strict"  # project default
    assert cfg.quality_gates.requirements is True
