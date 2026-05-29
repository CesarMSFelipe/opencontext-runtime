"""Tests for zero-config auto-detect."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.config import find_config, load_config_or_defaults


class TestFindConfig:
    """Parent-directory search for opencontext.yaml."""

    def test_finds_config_in_current_dir(self, tmp_path: Path) -> None:
        config = tmp_path / "opencontext.yaml"
        config.write_text("project:\n  name: test\n")
        found = find_config(tmp_path)
        assert found == config

    def test_finds_config_in_parent_dir(self, tmp_path: Path) -> None:
        config = tmp_path / "opencontext.yaml"
        config.write_text("project:\n  name: test\n")
        child = tmp_path / "subdir" / "deep"
        child.mkdir(parents=True)
        found = find_config(child)
        assert found == config

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        found = find_config(tmp_path)
        assert found is None

    def test_finds_config_up_to_10_levels(self, tmp_path: Path) -> None:
        # Create deeply nested structure
        deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        config = tmp_path / "opencontext.yaml"
        config.write_text("project:\n  name: deep-test\n")
        found = find_config(deep)
        assert found == config


class TestLoadConfigOrDefaults:
    """Zero-config entry point."""

    def test_loads_explicit_path(self, tmp_path: Path) -> None:
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("project:\n  name: explicit\n")
        cfg = load_config_or_defaults(config_file)
        assert cfg.project.name == "explicit"

    def test_loads_via_auto_detect(self, tmp_path: Path) -> None:
        config_file = tmp_path / "opencontext.yaml"
        config_file.write_text("project:\n  name: auto-detect\n")
        # Change to the tmp dir
        original_cwd = Path.cwd()
        import os

        os.chdir(str(tmp_path))
        try:
            cfg = load_config_or_defaults()
            assert cfg.project.name == "auto-detect"
        finally:
            os.chdir(str(original_cwd))

    def test_falls_back_to_defaults(self, tmp_path: Path) -> None:
        """With no config file, should return defaults."""
        original_cwd = Path.cwd()
        import os

        os.chdir(str(tmp_path))
        try:
            cfg = load_config_or_defaults()
            # Should have the directory name as project name
            assert cfg.project.name == tmp_path.name
        finally:
            os.chdir(str(original_cwd))

    def test_no_auto_detect_falls_back(self, tmp_path: Path) -> None:
        """With auto_detect=False and no file, should return defaults."""
        cfg = load_config_or_defaults(tmp_path / "nonexistent.yaml", auto_detect=False)
        # Falls back to CWD name (it's still a valid OpenContextConfig)
        assert cfg.project.name  # Name is always populated
