"""Single source of truth for per-agent filesystem layout.

Every agent's config directory, MCP config path, instructions filename, MCP shape,
skills directory, and AGENTS.md-honoring flag is declared here so the rest of the
configurator never hard-codes a path or root key.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.configurator.mcp_strategy import McpShape

MCP_LABEL = "opencontext"

MCP_SERVER_ENTRY: dict[str, object] = {
    "type": "stdio",
    "command": "opencontext",
    "args": ["serve", "--mcp"],
}

# Tool names auto-allowed for agents that support a permissions allow-list.
ALLOWED_TOOLS: tuple[str, ...] = (
    "mcp__opencontext__opencontext_search",
    "mcp__opencontext__opencontext_context",
    "mcp__opencontext__opencontext_callers",
    "mcp__opencontext__opencontext_callees",
    "mcp__opencontext__opencontext_impact",
    "mcp__opencontext__opencontext_node",
    "mcp__opencontext__opencontext_files",
    "mcp__opencontext__opencontext_status",
)


def agent_home(agent_id: str) -> Path:
    """Resolve the per-agent config directory under the current home."""

    home = Path.home()
    dirs: dict[str, Path] = {
        "claude-code": home / ".claude",
        "opencode": home / ".config" / "opencode",
        "kilo-code": home / ".config" / "kilo",
        "gemini-cli": home / ".gemini",
        "cursor": home / ".cursor",
        "vscode-copilot": home / ".vscode",
        "codex": home / ".codex",
        "windsurf": home / ".windsurf",
        "kimi-code": home / ".kimi",
        "kiro-ide": home / ".kiro",
        "kiro": home / ".kiro",
        "qwen-code": home / ".qwen",
        "openclaw": home / ".openclaw",
        "pi": home / ".pi",
        "antigravity": home / ".antigravity",
        "cline": home / ".cline",
        "roo": home / ".roo",
        "continue": home / ".continue",
        "goose": home / ".config" / "goose",
        "copilot-cli": home / ".copilot",
        "openhands": home / ".openhands",
        "aider": home / ".aider",
        "zed": home / ".config" / "zed",
    }
    return dirs.get(agent_id, home / f".{agent_id}")


# Filename of the MCP config inside the agent's config directory.
# gemini-cli and codex keep MCP config inside an existing settings/config file.
_MCP_FILENAME: dict[str, str] = {
    "gemini-cli": "settings.json",
    "codex": "config.toml",
    "continue": "config.yaml",
    "vscode-copilot": "mcp.json",
}


def mcp_config_path(agent_id: str) -> Path:
    """Resolve the MCP config file path for an agent."""

    return agent_home(agent_id) / _MCP_FILENAME.get(agent_id, "mcp.json")


# Instructions filename for agents that use a named file rather than AGENTS.md.
_INSTRUCTIONS_FILENAME: dict[str, str] = {
    "claude-code": "CLAUDE.md",
    "openclaw": "CLAUDE.md",
    "gemini-cli": "GEMINI.md",
    "antigravity": "GEMINI.md",
    "qwen-code": "QWEN.md",
}


def instructions_filename(agent_id: str) -> str:
    """Resolve the instructions filename, defaulting to AGENTS.md."""

    return _INSTRUCTIONS_FILENAME.get(agent_id, "AGENTS.md")


# Agents whose instructions root is the project tree rather than the agent's
# home directory (e.g. AGENTS.md / CLAUDE.md live next to the code).
PROJECT_SCOPED_INSTRUCTIONS: frozenset[str] = frozenset(
    {
        "codex",
        "opencode",
        "cursor",
        "windsurf",
        "vscode-copilot",
        "kilo-code",
        "kiro",
        "aider",
        "zed",
        "continue",
        "cline",
        "roo",
        "goose",
        "copilot-cli",
        "openhands",
    }
)


# MCP wire shape per agent. Anything not listed uses JSON ``mcpServers``.
_MCP_SHAPE: dict[str, McpShape] = {
    "vscode-copilot": McpShape.JSON_SERVERS,
    "copilot-cli": McpShape.JSON_SERVERS,
    "codex": McpShape.TOML_MCP_SERVERS,
    "continue": McpShape.YAML_MCP_SERVERS,
}


def mcp_shape(agent_id: str) -> McpShape:
    """Resolve the MCP wire shape for an agent."""

    return _MCP_SHAPE.get(agent_id, McpShape.JSON_MCP_SERVERS)


# Agents that honor a shared AGENTS.md convention.
_HONORS_AGENTS_MD: frozenset[str] = frozenset(
    {
        "codex",
        "opencode",
        "cursor",
        "windsurf",
        "vscode-copilot",
        "kilo-code",
        "kiro-ide",
        "kiro",
        "aider",
        "zed",
        "continue",
        "cline",
        "roo",
        "goose",
        "copilot-cli",
        "openhands",
        "pi",
        "kimi-code",
    }
)


def honors_agents_md(agent_id: str) -> bool:
    """Whether the agent reads a shared AGENTS.md file."""

    return agent_id in _HONORS_AGENTS_MD


def skills_dir(agent_id: str) -> Path:
    """Resolve the skills directory for an agent."""

    return agent_home(agent_id) / "skills"
