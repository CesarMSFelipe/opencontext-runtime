"""Per-agent adapters describing how to configure each AI coding tool.

An :class:`Adapter` is a read-only declaration assembled from
:mod:`opencontext_core.configurator.constants`. It tells the configurator which
files to write, the MCP wire shape, and whether the agent honors AGENTS.md.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from opencontext_core.configurator import constants
from opencontext_core.configurator.mcp_strategy import McpShape

# Agents the configurator knows how to set up.
KNOWN_AGENTS: tuple[str, ...] = (
    "claude-code",
    "opencode",
    "kilo-code",
    "gemini-cli",
    "cursor",
    "vscode-copilot",
    "codex",
    "windsurf",
    "kimi-code",
    "kiro-ide",
    "kiro",
    "qwen-code",
    "openclaw",
    "pi",
    "antigravity",
    "aider",
    "cline",
    "roo",
    "goose",
    "copilot-cli",
    "continue",
    "openhands",
    "zed",
)


@dataclass(frozen=True)
class Adapter:
    """Declarative configuration contract for one agent."""

    agent_id: str
    config_dir: Path
    instructions_filename: str
    instructions_project_scoped: bool
    honors_agents_md: bool
    mcp_config_path: Path
    mcp_shape: McpShape
    skills_dir: Path

    def instructions_path(self, project_root: Path) -> Path:
        """Where this agent's instructions file should be written."""

        root = project_root if self.instructions_project_scoped else self.config_dir
        return root / self.instructions_filename


def get_adapter(agent_id: str) -> Adapter:
    """Build the adapter for ``agent_id``.

    Path-resolving helpers read :func:`Path.home`, so adapters are constructed
    lazily to honor a monkeypatched home in tests.
    """

    return Adapter(
        agent_id=agent_id,
        config_dir=constants.agent_home(agent_id),
        instructions_filename=constants.instructions_filename(agent_id),
        instructions_project_scoped=agent_id in constants.PROJECT_SCOPED_INSTRUCTIONS,
        honors_agents_md=constants.honors_agents_md(agent_id),
        mcp_config_path=constants.mcp_config_path(agent_id),
        mcp_shape=constants.mcp_shape(agent_id),
        skills_dir=constants.skills_dir(agent_id),
    )


def iter_adapters() -> Iterator[Adapter]:
    """Yield an adapter for every known agent."""

    for agent_id in KNOWN_AGENTS:
        yield get_adapter(agent_id)
