"""Agent installer - configures OpenContext integration for many AI coding agents.

Detects installed agents and writes each one's configuration through the
:class:`~opencontext_core.configurator.service.Configurator`, which selects the
correct rules file (AGENTS.md / CLAUDE.md / GEMINI.md / QWEN.md) and the correct
MCP wire shape (JSON ``mcpServers`` / JSON ``servers`` / TOML / YAML) per agent,
merging into existing files without clobbering developer content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

# Single AgentTarget enum (was duplicated here) — re-export the canonical superset
# so every caller shares one definition.
from opencontext_core.adapters.agent_manifest import AgentTarget
from opencontext_core.configurator.constants import agent_home
from opencontext_core.configurator.filemerge import write_text_atomic
from opencontext_core.configurator.service import Configurator
from opencontext_core.paths import StorageMode, resolve_workspace_path

__all__ = ["AgentInstaller", "AgentTarget"]


class AgentInstaller:
    """Installs OpenContext integration for various AI agents.

    Thin wrapper over :class:`Configurator` that preserves the historical public
    surface (``install``, ``detect_installed_agents``) and the ``AgentTarget`` enum.
    """

    # Real, installable agents — excludes GENERIC (a meta-target for generic
    # instruction output, not an agent to configure).
    SUPPORTED_AGENTS: ClassVar[list[AgentTarget]] = [
        t for t in AgentTarget if t != AgentTarget.GENERIC
    ]

    @staticmethod
    def _get_agent_dir(target: AgentTarget) -> Path:
        """Get the config directory for a given agent target."""

        return agent_home(target.value)

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.opencontext_dir = resolve_workspace_path(self.project_root, StorageMode.local)
        self.storage_dir = self.opencontext_dir / "agent-configs"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._configurator = Configurator(project_root=self.project_root)

    def detect_installed_agents(self) -> list[AgentTarget]:
        """Auto-detect which agents are installed on the system."""

        detected: list[AgentTarget] = []
        for agent in self.SUPPORTED_AGENTS:
            if self._get_agent_dir(agent).exists():
                detected.append(agent)
        return detected

    def install(
        self,
        targets: list[AgentTarget] | None = None,
        location: str = "local",
        yes: bool = False,
    ) -> dict[str, Any]:
        """Install OpenContext integration for specified agents.

        Args:
            targets: List of agents to configure. If None, auto-detect.
            location: "global" or "local" config location.
            yes: Skip prompts if True.

        Returns:
            Installation report.
        """

        if targets is None:
            targets = self.detect_installed_agents()

        results = [self._configurator.configure_one(target.value, location) for target in targets]

        return {
            "status": "installed",
            "location": location,
            "project": str(self.project_root),
            "agents_configured": len(results),
            "results": results,
        }

    def _merge_json_config(self, path: Path, new_config: dict[str, Any]) -> None:
        """Deep-merge ``new_config`` into an existing JSON file, atomically."""

        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = {}
        merged = self._deep_merge(existing, new_config)
        write_text_atomic(path, json.dumps(merged, indent=2))

    @staticmethod
    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge two dictionaries."""

        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = AgentInstaller._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
