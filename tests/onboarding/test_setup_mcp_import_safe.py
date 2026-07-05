"""onboarding with setup_mcp=True is import-safe and wires MCP.

RED first: ``onboarding/service.py`` imports the non-existent symbol
``setup_mcp_for_opencode`` from ``mcp_stdio`` (caught + downgraded to a warning),
so MCP is never configured.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opencontext_core.onboarding.service import OnboardingOptions, OnboardingService


def _redirect_agent_home(monkeypatch: Any, home: Path) -> None:
    """Point AgentInstaller's per-agent config dirs at a temp home."""
    from opencontext_core import agent_installer

    monkeypatch.setattr(agent_installer.Path, "home", classmethod(lambda cls: home))


def test_setup_mcp_completes_without_import_error(tmp_path: Path, monkeypatch: Any) -> None:
    """setup_mcp=True must not surface an ImportError warning."""
    home = tmp_path / "home"
    home.mkdir()
    _redirect_agent_home(monkeypatch, home)

    service = OnboardingService()
    result = service.run(
        OnboardingOptions(
            root=tmp_path / "proj",
            active_clients=["opencode"],
            setup_mcp=True,
            force_agent_files=True,
        )
    )

    import_warnings = [
        w for w in result.warnings if "ImportError" in w or "setup_mcp_for_opencode" in w
    ]
    assert not import_warnings, f"MCP setup raised an import error: {import_warnings}"
    assert result.mcp_configured is True


def test_setup_mcp_writes_mcp_config_entry(tmp_path: Path, monkeypatch: Any) -> None:
    """setup_mcp=True must write a valid MCP config entry for the agent target."""
    home = tmp_path / "home"
    home.mkdir()
    _redirect_agent_home(monkeypatch, home)

    service = OnboardingService()
    service.run(
        OnboardingOptions(
            root=tmp_path / "proj",
            active_clients=["opencode"],
            setup_mcp=True,
            force_agent_files=True,
        )
    )

    # OpenCode's native config: ``opencode.json`` with a root ``mcp`` key.
    # (The historical ``mcp.json``/``mcpServers`` file is one OpenCode never reads.)
    mcp_path = home / ".config" / "opencode" / "opencode.json"
    assert mcp_path.exists(), "MCP config was not written for the detected agent target"
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert "opencontext" in data.get("mcp", {})


def test_setup_mcp_false_does_not_configure(tmp_path: Path, monkeypatch: Any) -> None:
    """When setup_mcp is False, mcp_configured stays False."""
    home = tmp_path / "home"
    home.mkdir()
    _redirect_agent_home(monkeypatch, home)

    service = OnboardingService()
    result = service.run(
        OnboardingOptions(
            root=tmp_path / "proj",
            active_clients=["opencode"],
            setup_mcp=False,
            force_agent_files=True,
        )
    )
    assert result.mcp_configured is False
