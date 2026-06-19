"""Tests for installation manager."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.install_manager import InstallationManager, InstallProfile, InstallState


class TestInstallationManager:
    """Test installation manager."""

    @pytest.fixture
    def manager(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> InstallationManager:
        """Create manager with a temp state dir and an isolated working dir."""
        state_dir = tmp_path / ".config" / "opencontext"
        monkeypatch.setattr(InstallationManager, "STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        return InstallationManager()

    def test_init(self, manager: InstallationManager) -> None:
        assert manager.system in ["Darwin", "Linux", "Windows"]

    def test_not_installed(self, manager: InstallationManager) -> None:
        assert not manager._is_installed()

    def test_install_minimal(self, manager: InstallationManager) -> None:
        result = manager.install(
            profile=InstallProfile.MINIMAL,
            backup=False,
            yes=True,
        )
        assert result["status"] == "installed"
        assert "mcp" in result["components"]
        assert manager._is_installed()

    def test_install_global_once(self, manager: InstallationManager) -> None:
        # Global integration (MCP/agents/profiles) is installed once per machine;
        # a second install only does per-project setup, unless force_global.
        first = manager.install(profile=InstallProfile.MINIMAL, backup=False, yes=True)
        assert first["global_skipped"] is False
        second = manager.install(profile=InstallProfile.MINIMAL, backup=False, yes=True)
        assert second["global_skipped"] is True
        forced = manager.install(
            profile=InstallProfile.MINIMAL, backup=False, yes=True, force_global=True
        )
        assert forced["global_skipped"] is False

    def test_install_full(self, manager: InstallationManager) -> None:
        result = manager.install(
            profile=InstallProfile.FULL,
            backup=False,
            yes=True,
        )
        assert result["status"] == "installed"
        assert len(result["components"]) > 0

    def test_update_not_installed(self, manager: InstallationManager) -> None:
        result = manager.update(check_only=True)
        assert result["status"] == "not_installed"

    def test_verify_not_installed(self, manager: InstallationManager) -> None:
        result = manager.verify()
        assert result["status"] == "not_installed"
        assert not result["healthy"]

    def test_uninstall_not_installed(self, manager: InstallationManager) -> None:
        result = manager.uninstall(yes=True)
        assert result["status"] == "not_installed"

    def test_list_installed_empty(self, manager: InstallationManager) -> None:
        result = manager.list_installed()
        assert result["status"] == "not_installed"

    def test_state_save_load(self, manager: InstallationManager) -> None:
        state = InstallState(
            version="1.0.0",
            components=["mcp", "agents"],
            agents=["claude-code"],
        )
        manager._save_state(state)
        loaded = manager._load_state()
        assert loaded is not None
        assert loaded.version == "1.0.0"
        assert loaded.components == ["mcp", "agents"]
        assert loaded.agents == ["claude-code"]

    def test_verify_installed(self, manager: InstallationManager) -> None:
        manager.install(profile=InstallProfile.MINIMAL, backup=False, yes=True)
        result = manager.verify()
        assert result["status"] == "verified"

    def test_update_check(self, manager: InstallationManager) -> None:
        manager.install(profile=InstallProfile.MINIMAL, backup=False, yes=True)
        result = manager.update(check_only=True)
        assert result["status"] == "checked"
        assert "current_version" in result
