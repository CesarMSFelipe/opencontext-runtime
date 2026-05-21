"""Tests for plugin system."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.plugin_system import PluginInfo, PluginRegistry


class TestPluginRegistry:
    """Test plugin registry."""

    def test_discover_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            PluginRegistry, "__init__",
            lambda self, plugins_dir=None: setattr(self, "plugins_dir", tmp_path) or setattr(self, "_plugins", {}) or setattr(self, "_commands", {}) or setattr(self, "_hooks", {})
        )
        registry = PluginRegistry(tmp_path)
        plugins = registry.discover()
        assert plugins == []

    def test_enable_disable_nonexistent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            PluginRegistry, "__init__",
            lambda self, plugins_dir=None: setattr(self, "plugins_dir", tmp_path) or setattr(self, "_plugins", {}) or setattr(self, "_commands", {}) or setattr(self, "_hooks", {})
        )
        registry = PluginRegistry(tmp_path)
        assert not registry.enable("nonexistent")
        assert not registry.disable("nonexistent")

    def test_register_command(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            PluginRegistry, "__init__",
            lambda self, plugins_dir=None: setattr(self, "plugins_dir", tmp_path) or setattr(self, "_plugins", {}) or setattr(self, "_commands", {}) or setattr(self, "_hooks", {})
        )
        registry = PluginRegistry(tmp_path)
        registry.register_command("test", lambda: "result")
        assert "test" in registry.list_commands()
        assert registry.execute_command("test") == "result"

    def test_register_hook(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            PluginRegistry, "__init__",
            lambda self, plugins_dir=None: setattr(self, "plugins_dir", tmp_path) or setattr(self, "_plugins", {}) or setattr(self, "_commands", {}) or setattr(self, "_hooks", {})
        )
        registry = PluginRegistry(tmp_path)
        registry.register_hook("event", lambda x: x * 2)
        results = registry.trigger_hook("event", 5)
        assert results == [10]
