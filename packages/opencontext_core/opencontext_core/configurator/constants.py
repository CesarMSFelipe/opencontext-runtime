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
    # --workflow-tools: the rendered client instructions tell every agent to
    # call opencontext_run and finish agent_execute handoffs via
    # opencontext_session_apply, so the registered server must allowlist the
    # workflow tools. Symbol-write tools stay behind their own opt-in.
    "args": ["mcp", "--workflow-tools"],
}

# The opencontext MCP read tools (knowledge graph) in claude-code allow-list form
# (``mcp__<server>__<tool>``). These let an agent traverse the KG instead of
# grepping the tree.
KG_READ_TOOLS: tuple[str, ...] = (
    "mcp__opencontext__opencontext_search",
    "mcp__opencontext__opencontext_context",
    "mcp__opencontext__opencontext_callers",
    "mcp__opencontext__opencontext_callees",
    "mcp__opencontext__opencontext_impact",
    "mcp__opencontext__opencontext_node",
    "mcp__opencontext__opencontext_files",
    "mcp__opencontext__opencontext_status",
)

# The opencontext MCP memory tools (proactive persistent memory).
MEMORY_TOOLS: tuple[str, ...] = (
    "mcp__opencontext__opencontext_memory_save",
    "mcp__opencontext__opencontext_memory_search",
    "mcp__opencontext__opencontext_memory_context",
    "mcp__opencontext__opencontext_memory_judge",
)

# Tool names auto-allowed for agents that support a permissions allow-list.
ALLOWED_TOOLS: tuple[str, ...] = KG_READ_TOOLS


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
        "trae": home / ".trae",
        "hermes": home / ".hermes",
    }
    return dirs.get(agent_id, home / f".{agent_id}")


# Filename of the MCP config inside the agent's config directory.
# Listed agents keep MCP config in a specific named file; anything not listed defaults to mcp.json.
_MCP_FILENAME: dict[str, str] = {
    "gemini-cli": "settings.json",
    "codex": "config.toml",
    "continue": "config.yaml",
    "vscode-copilot": "mcp.json",
    # OpenCode only reads opencode.json(c); a sibling mcp.json is ignored.
    "opencode": "opencode.json",
}


def mcp_config_path(agent_id: str) -> Path:
    """Resolve the MCP config file path for an agent."""

    return agent_home(agent_id) / _MCP_FILENAME.get(agent_id, "mcp.json")


# Agents that also read a project-scoped (repo-root) MCP config, so a single repo
# can expose the OpenContext tools without touching the user's global config.
# Claude Code reads ``<repo>/.mcp.json``; the home file alone does not enable the
# server per-repo. Value is the project-relative filename.
_PROJECT_MCP_FILENAME: dict[str, str] = {
    "claude-code": ".mcp.json",
}


def project_mcp_filename(agent_id: str) -> str | None:
    """Project-relative MCP config filename for an agent, or None if it has none."""

    return _PROJECT_MCP_FILENAME.get(agent_id)


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


# Paths kept out of agent context by default — secrets, build output, vendored
# deps. One list fans out to each agent's native ignore file so the agent never
# reads them, reinforcing OpenContext's secret-redaction goal at the source.
DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "secrets/",
    "*.secret",
    "node_modules/",
    "dist/",
    "build/",
    ".venv/",
    "venv/",
    "__pycache__/",
    ".git/",
    ".storage/",
    "*.sqlite",
    "*.db",
)

# Agents with a native project-root "don't read these paths" file.
_IGNORE_FILENAME: dict[str, str] = {
    "cursor": ".cursorignore",
    "gemini-cli": ".geminiignore",
    "aider": ".aiderignore",
    "cline": ".clineignore",
    "roo": ".rooignore",
    "windsurf": ".codeiumignore",
    "trae": ".traeignore",
}


def ignore_filename(agent_id: str) -> str | None:
    """Native ignore-file name for an agent, or None if it has none."""

    return _IGNORE_FILENAME.get(agent_id)


# Reusable slash-commands written as native command files so OpenContext's core
# actions are one keystroke in the agent. (name, description, prompt body);
# ``$ARGUMENTS`` is the agent's task-text placeholder. These are whole files we
# own (prefixed ``oc-``), so uninstall simply deletes them.
OPENCONTEXT_COMMANDS: tuple[tuple[str, str, str], ...] = (
    (
        "oc-context",
        "Build verified, minimal context for a task",
        "Use the `opencontext_context` MCP tool to build verified, minimal context, "
        "then answer using only it.\n\nTask: $ARGUMENTS",
    ),
    (
        "oc-impact",
        "Assess blast radius before changing a symbol",
        "Use the `opencontext_impact` MCP tool to report what changing this symbol "
        "affects (callers, files, tests, risk) before editing.\n\nSymbol: $ARGUMENTS",
    ),
    (
        "oc-new",
        "Start a new SDD change — runs the full flow automatically",
        "Start a new spec-driven change and drive the whole flow in order by "
        "SPAWNING each phase's persona subagent with the Task tool (the main "
        "thread sequences and gates, it does not do the work):\n"
        "explore -> `subagent_type: oc-explorer`; propose -> "
        "`subagent_type: oc-orchestrator`; spec -> `subagent_type: oc-requirements`; "
        "tasks -> `subagent_type: oc-planner`; design -> `subagent_type: oc-architect`; "
        "approval gate; apply (tests first) -> `subagent_type: oc-tester` then "
        "`subagent_type: oc-builder`; verify -> `subagent_type: oc-harness-verifier`; "
        "archive -> `subagent_type: oc-archivist`.\n"
        "Memory loop every phase: derive a change `<slug>`; each persona PRIMES at "
        "start with `opencontext_memory_context` for `change:<slug>` and SAVES at "
        "end with `opencontext_memory_save` (`key`/`tags` = `change:<slug>`; layer "
        "SEMANTIC for facts, PROCEDURAL for patterns, FAILURE for errors).\n"
        "Build context with `opencontext_context` and check `opencontext_impact` "
        "before any edit; pause for approval before writing code.\n\n"
        "Change: $ARGUMENTS",
    ),
)

# Agents with a project-scoped Markdown command directory (relative to project root).
_COMMAND_DIR: dict[str, str] = {
    "claude-code": ".claude/commands",
}


def command_dir(agent_id: str) -> str | None:
    """Project-relative slash-command directory for an agent, or None."""

    return _COMMAND_DIR.get(agent_id)


# Agents with a project-scoped subagent/persona directory (relative to project root).
_PERSONA_DIR: dict[str, str] = {
    "claude-code": ".claude/agents",
}


def persona_dir(agent_id: str) -> str | None:
    """Project-relative persona (subagent) directory for an agent, or None."""

    return _PERSONA_DIR.get(agent_id)


_HIDDEN_DELEGATION_DIRS: dict[str, str] = {
    "claude-code": ".claude/agents/.opencontext-delegates",
}


def hidden_delegation_dir(agent_id: str) -> str | None:
    """Return the hidden delegation subdirectory for agent_id, or None if unsupported."""
    return _HIDDEN_DELEGATION_DIRS.get(agent_id)


# Agents with a global (home-dir-relative) agents directory — persona .md files go here.
# Key: agent_id → subdir within agent_home(agent_id).
_GLOBAL_AGENTS_SUBDIR: dict[str, str] = {
    "opencode": "agents",
}


def global_agents_subdir(agent_id: str) -> str | None:
    """Subdir within config_dir where global persona files go, or None."""

    return _GLOBAL_AGENTS_SUBDIR.get(agent_id)


# Agents whose instructions root is the project tree rather than the agent's
# home directory (e.g. AGENTS.md / CLAUDE.md live next to the code).
# Every AGENTS.md-honoring agent is project-scoped (AGENTS.md lives at the project
# root, not the agent's home dir). Must stay in sync with _HONORS_AGENTS_MD below —
# previously kiro-ide, pi, and kimi-code honored AGENTS.md but were missing here, so
# their instructions landed in the home dir instead of the project root.
PROJECT_SCOPED_INSTRUCTIONS: frozenset[str] = frozenset(
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


# MCP wire shape per agent. Anything not listed uses JSON ``mcpServers``.
_MCP_SHAPE: dict[str, McpShape] = {
    "vscode-copilot": McpShape.JSON_SERVERS,
    "copilot-cli": McpShape.JSON_SERVERS,
    "codex": McpShape.TOML_MCP_SERVERS,
    "continue": McpShape.YAML_MCP_SERVERS,
    "opencode": McpShape.JSON_OPENCODE_MCP,
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
