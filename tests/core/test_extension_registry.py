"""Tests for the Extension Marketplace — manifest validation, search, install, list, remove."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.workflow.extension_registry import BUILTIN_INDEX, ExtensionRegistry
from opencontext_core.workflow.extensions import ExtensionManifest


# ── ExtensionManifest ────────────────────────────────────────────────────────


def test_manifest_valid() -> None:
    """Valid manifest fields produce a clean model."""
    m = ExtensionManifest.from_dict({
        "name": "my-extension",
        "version": "1.0.0",
        "description": "A test extension.",
        "author": "test-author",
    })
    assert m.name == "my-extension"
    assert m.version == "1.0.0"
    assert m.author == "test-author"


def test_manifest_invalid_name() -> None:
    """Non-kebab name raises ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExtensionManifest.from_dict({"name": "bad name!", "version": "1.0.0"})


def test_manifest_invalid_version() -> None:
    """Non-SemVer version raises ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExtensionManifest.from_dict({"name": "ok-name", "version": "v1"})


def test_manifest_from_yaml(tmp_path: Path) -> None:
    """from_yaml() loads and validates a manifest from disk."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        "name: yaml-ext\nversion: 2.1.0\ndescription: Loaded from YAML\nauthor: tester\n",
        encoding="utf-8",
    )
    m = ExtensionManifest.from_yaml(manifest_file)
    assert m.name == "yaml-ext"
    assert m.version == "2.1.0"


# ── ExtensionRegistry.search ─────────────────────────────────────────────────


def test_search_empty_query_returns_all() -> None:
    """Empty query returns all registry entries."""
    registry = ExtensionRegistry()
    results = registry.search()
    assert len(results) == len(BUILTIN_INDEX)


def test_search_by_name() -> None:
    """Search by partial name returns matching entries."""
    registry = ExtensionRegistry()
    results = registry.search("cost")
    assert any("cost" in r["name"] for r in results)


def test_search_by_tag() -> None:
    """Search by tag returns extensions with that tag."""
    registry = ExtensionRegistry()
    results = registry.search("review")
    assert len(results) >= 1


def test_search_no_match_returns_empty() -> None:
    """Search with no match returns empty list."""
    registry = ExtensionRegistry()
    results = registry.search("xxxxxxxxxnonexistentxxxxxx")
    assert results == []


# ── ExtensionRegistry.install / list / remove ────────────────────────────────


def test_install_creates_manifest_file(tmp_path: Path) -> None:
    """install() creates a manifest.yaml in the extensions directory."""
    registry = ExtensionRegistry()
    ext_dir = registry.install("strict-review", root=tmp_path)
    assert (ext_dir / "manifest.yaml").exists()


def test_install_unknown_extension_raises(tmp_path: Path) -> None:
    """install() raises ValueError for unknown extension names."""
    registry = ExtensionRegistry()
    with pytest.raises(ValueError, match="not found"):
        registry.install("nonexistent-extension-xyz", root=tmp_path)


def test_list_installed_empty_when_none(tmp_path: Path) -> None:
    """list_installed() returns empty list when no extensions are installed."""
    registry = ExtensionRegistry()
    assert registry.list_installed(root=tmp_path) == []


def test_install_then_list(tmp_path: Path) -> None:
    """Installed extensions appear in list_installed()."""
    registry = ExtensionRegistry()
    registry.install("strict-review", root=tmp_path)
    installed = registry.list_installed(root=tmp_path)
    assert len(installed) == 1
    assert installed[0].name == "strict-review"


def test_remove_installed_extension(tmp_path: Path) -> None:
    """remove() deletes the extension directory and returns True."""
    registry = ExtensionRegistry()
    registry.install("cost-guard", root=tmp_path)
    assert registry.remove("cost-guard", root=tmp_path) is True
    assert registry.list_installed(root=tmp_path) == []


def test_remove_nonexistent_returns_false(tmp_path: Path) -> None:
    """remove() returns False when extension is not installed."""
    registry = ExtensionRegistry()
    assert registry.remove("not-installed", root=tmp_path) is False


# ── Extension preset resolution ──────────────────────────────────────────────


def test_extension_presets_appear_in_find_presets(tmp_path: Path) -> None:
    """Presets from installed extensions are picked up by find_presets()."""
    from opencontext_core.workflow.presets import find_presets

    # Create extension with a preset
    ext_dir = tmp_path / ".opencontext" / "extensions" / "my-ext" / "presets"
    ext_dir.mkdir(parents=True)
    (ext_dir / "ext-preset.yaml").write_text(
        "name: ext-preset\ndescription: From extension\nbase:\n  x: 1\n",
        encoding="utf-8",
    )

    presets = find_presets(root=tmp_path)
    names = {p.name for p in presets}
    assert "ext-preset" in names


def test_project_preset_overrides_extension_preset(tmp_path: Path) -> None:
    """Project-level preset takes priority over extension preset with same name."""
    from opencontext_core.workflow.presets import find_presets

    # Extension preset
    ext_presets = tmp_path / ".opencontext" / "extensions" / "my-ext" / "presets"
    ext_presets.mkdir(parents=True)
    (ext_presets / "shared.yaml").write_text(
        "name: shared\ndescription: Extension version\nbase:\n  source: extension\n",
        encoding="utf-8",
    )

    # Project preset (higher priority)
    proj_presets = tmp_path / ".opencontext" / "presets"
    proj_presets.mkdir(parents=True)
    (proj_presets / "shared.yaml").write_text(
        "name: shared\ndescription: Project version\nbase:\n  source: project\n",
        encoding="utf-8",
    )

    presets = find_presets(root=tmp_path)
    shared = next((p for p in presets if p.name == "shared"), None)
    assert shared is not None
    assert shared.base.get("source") == "project"
