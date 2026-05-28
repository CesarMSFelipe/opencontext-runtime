"""Tests for the workflow preset system."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.workflow.presets import (
    BUILTIN_PRESETS,
    Preset,
    compose,
    find_presets,
    load_preset,
)


# ── find_presets ─────────────────────────────────────────────────────────────


def test_find_presets_returns_builtin_presets() -> None:
    """find_presets always includes the built-in core presets."""
    presets = find_presets()
    names = {p.name for p in presets}
    assert "strict-tdd" in names
    assert "air-gapped" in names
    assert "cheap" in names


def test_find_presets_loads_from_project_dir(tmp_path: Path) -> None:
    """find_presets loads YAML presets from .opencontext/presets/."""
    preset_dir = tmp_path / ".opencontext" / "presets"
    preset_dir.mkdir(parents=True)
    (preset_dir / "my-preset.yaml").write_text(
        "name: my-preset\ndescription: Custom preset\nbase:\n  foo: bar\nstrategy: replace\n",
        encoding="utf-8",
    )
    presets = find_presets(root=tmp_path)
    names = {p.name for p in presets}
    assert "my-preset" in names
    assert "strict-tdd" in names  # built-ins still present


def test_find_presets_project_overrides_builtin(tmp_path: Path) -> None:
    """A project preset with the same name as a builtin overrides it."""
    preset_dir = tmp_path / ".opencontext" / "presets"
    preset_dir.mkdir(parents=True)
    (preset_dir / "strict-tdd.yaml").write_text(
        "name: strict-tdd\ndescription: Custom override\nbase:\n  x: 1\n",
        encoding="utf-8",
    )
    presets = find_presets(root=tmp_path)
    match = next((p for p in presets if p.name == "strict-tdd"), None)
    assert match is not None
    assert match.description == "Custom override"


# ── load_preset ──────────────────────────────────────────────────────────────


def test_load_preset_returns_builtin() -> None:
    preset = load_preset("strict-tdd")
    assert preset is not None
    assert preset.name == "strict-tdd"


def test_load_preset_returns_none_for_unknown() -> None:
    assert load_preset("nonexistent-preset-xyz") is None


# ── compose ──────────────────────────────────────────────────────────────────


def test_compose_replace_strategy() -> None:
    """Replace strategy: preset keys override base keys (deep merge)."""
    base = {"security": {"mode": "open"}, "extra": "stays"}
    preset = Preset(
        name="test",
        base={"security": {"mode": "air_gapped"}},
        strategy="replace",
    )
    result = compose(base, preset)
    assert result["security"]["mode"] == "air_gapped"
    assert result["extra"] == "stays"


def test_compose_does_not_mutate_base() -> None:
    """compose() returns a new dict and does not mutate the input."""
    base = {"key": "original"}
    preset = Preset(name="test", base={"key": "changed"}, strategy="replace")
    result = compose(base, preset)
    assert base["key"] == "original"
    assert result["key"] == "changed"


def test_compose_append_strategy_for_lists() -> None:
    """Append strategy: list values are appended."""
    base = {"items": ["a", "b"]}
    preset = Preset(name="test", base={"items": ["c"]}, strategy="append")
    result = compose(base, preset)
    assert result["items"] == ["a", "b", "c"]


def test_compose_prepend_strategy_for_lists() -> None:
    """Prepend strategy: list values are prepended."""
    base = {"items": ["a", "b"]}
    preset = Preset(name="test", base={"items": ["x"]}, strategy="prepend")
    result = compose(base, preset)
    assert result["items"] == ["x", "a", "b"]


def test_compose_strict_tdd_preset() -> None:
    """Applying strict-tdd preset sets tdd_mode to strict."""
    preset = BUILTIN_PRESETS["strict-tdd"]
    result = compose({}, preset)
    assert result["sdd"]["tdd_mode"] == "strict"
