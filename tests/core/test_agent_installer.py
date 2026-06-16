"""Tests for agent installer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.agent_installer import AgentInstaller, AgentTarget


@pytest.fixture
def temp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use a temporary home directory for tests."""

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


class TestAgentInstaller:
    """Test agent installer functionality."""

    def test_detect_installed_agents_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Detect agents when none are installed."""

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        installer = AgentInstaller()
        detected = installer.detect_installed_agents()
        assert detected == []

    def test_detect_installed_agents_some(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Detect agents when some are installed."""

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # Create some agent config directories
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".config" / "opencode").mkdir(parents=True)
        (tmp_path / ".cursor").mkdir()

        installer = AgentInstaller()
        detected = installer.detect_installed_agents()
        assert len(detected) == 3
        assert AgentTarget.CLAUDE_CODE in detected
        assert AgentTarget.OPENCODE in detected
        assert AgentTarget.CURSOR in detected

    def test_install_claude(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Install Claude Code configuration."""

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        installer = AgentInstaller()
        result = installer.install(targets=[AgentTarget.CLAUDE_CODE], location="global")

        assert result["status"] == "installed"
        assert result["agents_configured"] == 1
        assert result["results"][0]["agent"] == "claude-code"
        assert result["results"][0]["status"] == "configured"

        # Check files were created
        claude_dir = tmp_path / ".claude"
        assert (claude_dir / "mcp.json").exists()
        assert (claude_dir / "CLAUDE.md").exists()
        assert (claude_dir / "settings.json").exists()

    def test_install_opencode(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Install OpenCode configuration."""

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        installer = AgentInstaller(project_root=tmp_path)
        result = installer.install(targets=[AgentTarget.OPENCODE], location="global")

        assert result["status"] == "installed"
        assert result["agents_configured"] == 1
        assert result["results"][0]["agent"] == "opencode"

        # Check files were created
        config_dir = tmp_path / ".config" / "opencode"
        assert (config_dir / "mcp.json").exists()
        assert (config_dir / "agents" / "sdd-orchestrator.json").exists()

    def test_all_agents_supported(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """All 14 agents now have config generators."""

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        installer = AgentInstaller(project_root=tmp_path)
        result = installer.install(targets=list(AgentTarget), location="global")

        assert len(result["results"]) == len(list(AgentTarget))
        for r in result["results"]:
            assert r["status"] == "configured", f"{r['agent']} was not configured"
        assert result["agents_configured"] == len(list(AgentTarget))

    def test_merge_json_config(self, tmp_path: Path) -> None:
        """Test JSON config merging."""

        path = tmp_path / "test.json"
        path.write_text(json.dumps({"existing": "value", "nested": {"a": 1}}), encoding="utf-8")

        installer = AgentInstaller()
        installer._merge_json_config(path, {"new": "value", "nested": {"b": 2}})

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["existing"] == "value"
        assert data["new"] == "value"
        assert data["nested"]["a"] == 1
        assert data["nested"]["b"] == 2

    def test_mcp_config_content(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify MCP config has correct server settings."""

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        installer = AgentInstaller()
        installer.install(targets=[AgentTarget.CLAUDE_CODE], location="global")

        mcp_path = tmp_path / ".claude" / "mcp.json"
        mcp_config = json.loads(mcp_path.read_text(encoding="utf-8"))

        assert "mcpServers" in mcp_config
        assert "opencontext" in mcp_config["mcpServers"]
        server = mcp_config["mcpServers"]["opencontext"]
        assert server["type"] == "stdio"
        assert server["command"] == "opencontext"
        assert server["args"] == ["serve", "--mcp"]

    def test_permissions_content(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify permissions config lists OpenContext tools."""

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        installer = AgentInstaller()
        installer.install(targets=[AgentTarget.CLAUDE_CODE], location="global")

        settings_path = tmp_path / ".claude" / "settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))

        assert "permissions" in settings
        assert "allow" in settings["permissions"]
        allowed = settings["permissions"]["allow"]
        assert any("opencontext_search" in a for a in allowed)
        assert any("opencontext_context" in a for a in allowed)
        assert any("opencontext_impact" in a for a in allowed)
