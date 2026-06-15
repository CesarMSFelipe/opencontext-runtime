"""Configure existing AI coding agents with the right files and MCP shape.

``Configurator`` is the single entry point. For each requested agent it:
- writes the MCP server entry in the agent's native shape,
- injects a managed instructions block into the agent's rules file
  (AGENTS.md / CLAUDE.md / GEMINI.md / QWEN.md, project- or home-scoped),
- writes any agent-specific extras (claude permissions, opencode profile),

all through the safe-merge primitives so user-owned content is never clobbered.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from opencontext_core.configurator import constants
from opencontext_core.configurator.adapter import Adapter, get_adapter, iter_adapters
from opencontext_core.configurator.filemerge import (
    inject_managed_section,
    merge_mcp_config_file,
    write_text_atomic,
)
from opencontext_core.configurator.mcp_strategy import write_mcp_servers

InstructionsBuilder = Callable[[str], str]


class Configurator:
    """Write per-agent configuration without overwriting developer files."""

    def __init__(
        self,
        project_root: str | Path = ".",
        *,
        instructions_builder: InstructionsBuilder | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self._build_instructions = instructions_builder or _default_instructions

    def detect_installed(self) -> list[str]:
        """Return the ids of known agents whose config directory exists."""

        return [a.agent_id for a in iter_adapters() if a.config_dir.exists()]

    def configure(self, agents: list[str], scope: str = "local") -> dict[str, Any]:
        """Configure ``agents`` and return a structured report."""

        results = [self.configure_one(agent_id, scope) for agent_id in agents]
        configured = sum(1 for r in results if r["status"] == "configured")
        return {
            "status": "configured",
            "scope": scope,
            "project": str(self.project_root),
            "agents_configured": configured,
            "results": results,
        }

    def configure_one(self, agent_id: str, scope: str = "local") -> dict[str, Any]:
        """Configure a single agent; returns its per-agent result entry."""

        adapter = get_adapter(agent_id)
        files: list[str] = []

        files.extend(self._write_mcp(adapter))
        files.append(self._write_instructions(adapter))
        files.extend(self._write_extras(adapter))

        return {"agent": agent_id, "status": "configured", "files": files}

    # ------------------------------------------------------------------

    def _write_mcp(self, adapter: Adapter) -> list[str]:
        path = adapter.mcp_config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        servers = {constants.MCP_LABEL: dict(constants.MCP_SERVER_ENTRY)}
        write_mcp_servers(path, servers, shape=adapter.mcp_shape)
        return [str(path)]

    def _write_instructions(self, adapter: Adapter) -> str:
        path = adapter.instructions_path(self.project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self._build_instructions(adapter.agent_id)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        merged = inject_managed_section(existing, "instructions", content)
        write_text_atomic(path, merged)
        return str(path)

    def _write_extras(self, adapter: Adapter) -> list[str]:
        files: list[str] = []
        if adapter.agent_id in {"claude-code", "openclaw"}:
            files.extend(self._write_claude_permissions(adapter))
        if adapter.agent_id == "opencode":
            files.extend(self._write_opencode_profile(adapter))
        return files

    def _write_claude_permissions(self, adapter: Adapter) -> list[str]:
        if adapter.agent_id != "claude-code":
            return []
        path = adapter.config_dir / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = {}
        existing_allow = existing.get("permissions", {}).get("allow", [])
        allow = list(dict.fromkeys([*existing_allow, *constants.ALLOWED_TOOLS]))
        existing.setdefault("permissions", {})["allow"] = allow
        write_text_atomic(path, json.dumps(existing, indent=2) + "\n")
        return [str(path)]

    def _write_opencode_profile(self, adapter: Adapter) -> list[str]:
        profile_dir = adapter.config_dir / "agents"
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile = {
            "name": "sdd-orchestrator",
            "description": "OpenContext SDD orchestrator with knowledge graph",
            "system_prompt": _orchestrator_prompt(),
            "tools": ["mcp__opencontext__*"],
        }
        path = profile_dir / "sdd-orchestrator.json"
        write_text_atomic(path, json.dumps(profile, indent=2) + "\n")
        return [str(path)]


def configure_mcp_only(agent_id: str, servers: dict[str, Any]) -> bool:
    """Write only the MCP config for ``agent_id`` in its native shape."""

    adapter = get_adapter(agent_id)
    adapter.mcp_config_path.parent.mkdir(parents=True, exist_ok=True)
    return write_mcp_servers(adapter.mcp_config_path, servers, shape=adapter.mcp_shape)


def merge_json_mcp(path: Path, servers: dict[str, Any], *, root_key: str = "mcpServers") -> bool:
    """Backwards-compatible JSON MCP merge helper."""

    return merge_mcp_config_file(path, servers, root_key=root_key)


# ----------------------------------------------------------------------
# Default content
# ----------------------------------------------------------------------

_CLI_REFERENCE = """### OpenContext CLI Reference

| Category | Command | Purpose |
|----------|---------|---------|
| **Health** | `opencontext verify` | Run all health checks |
| | `opencontext verify --json` | CI-friendly JSON output |
| | `opencontext doctor` | Deep runtime diagnostics |
| **Updates** | `opencontext update` | Check for newer version (24h cache) |
| | `opencontext update --force` | Skip cache |
| | `opencontext upgrade` | Install latest version |
| **Plugins** | `opencontext plugin search` | Browse available plugins |
| | `opencontext plugin install <name>` | Install from registry |
| | `opencontext plugin install <name> --github owner/repo` | Install from GitHub |
| | `opencontext plugin install <name> --url <url>` | Install from URL |
| | `opencontext plugin update` | Check for plugin updates |
| | `opencontext plugin info <name>` | Show plugin details |
| | `opencontext plugin list --json` | Machine-readable list |
| **Config** | `opencontext config wizard` | Interactive setup |
| | `opencontext config reconfigure plugins` | Browse & install plugins |
| | `opencontext config backup` | Manual backup |
| | `opencontext config restore <id>` | Rollback config |
| | `opencontext config show` | View current config |
| **KG** | `opencontext pack . --query "<task>"` | Generate context pack |
| | `opencontext index .` | Index project |
| **Setup** | `opencontext init` | Create project config |
| | `opencontext install` | Full project setup |
|"""

_KG_SECTION = """## Knowledge Graph (MCP Tools)

OpenContext indexes your project into a queryable knowledge graph with call analysis.

| Tool | Use For |
|------|---------|
| `opencontext_search` | Find symbols by name |
| `opencontext_context` | Build relevant code context for a task |
| `opencontext_callers` | Trace call flow (who calls a function) |
| `opencontext_callees` | Trace call flow (what a function calls) |
| `opencontext_impact` | Check what's affected before editing |
| `opencontext_node` | Get a single symbol's details |
| `opencontext_files` | Get indexed file structure |
| `opencontext_status` | Check index health |

### Rules

1. Use `opencontext_context` for exploration questions
2. Do NOT re-read files that `opencontext_context` already returned
3. Check `opencontext_impact` before making changes
4. Run `opencontext verify` if something seems wrong
"""

_HEALTH_SECTION = """## Health & Maintenance

- Run `opencontext verify` to check all components are working
- Run `opencontext update` to check for OpenContext updates
- Run `opencontext upgrade` to install the latest version
- Run `opencontext plugin update` to update all plugins
- Run `opencontext config backup` before risky configuration changes
"""

_SDD_SECTION = """## SDD Workflow

This project supports Spec-Driven Development.

- Run `opencontext init` to initialize SDD if not done
- Use `/sdd-new <change>` to start a new change
- The orchestrator runs: explore -> propose -> spec -> design -> tasks -> apply -> verify -> archive
"""

_SECURITY_SECTION = """## Security

- All tool executions require approval by default
- External providers are disabled in secure mode
- Context redaction is applied automatically
"""

_PREFIX = """# OpenContext Integration

OpenContext provides a semantic knowledge graph, health checks, plugin ecosystem,
and SDD orchestration for this project. Use the MCP tools directly.

"""


def _default_instructions(agent_id: str) -> str:
    """Build the managed instructions body for an agent."""

    return (
        _PREFIX
        + _KG_SECTION
        + _CLI_REFERENCE
        + "\n"
        + _HEALTH_SECTION
        + _SDD_SECTION
        + _SECURITY_SECTION
    )


def _orchestrator_prompt() -> str:
    return """You are the OpenContext SDD Orchestrator.

Your role is to coordinate Spec-Driven Development workflows using
the OpenContext knowledge graph and persistent memory.

## Principles

1. **Thin orchestrator thread**: Delegate all real work to sub-agents
2. **Context-aware**: Use the knowledge graph to understand code before planning
3. **Security-first**: All actions go through approval gates
4. **Teaching-oriented**: Explain WHY, not just WHAT

## SDD Workflow

```
explore -> propose -> spec -> design -> tasks -> apply -> verify -> archive
```

For each phase:
1. Load relevant context from the knowledge graph
2. Delegate to appropriate sub-agent
3. Verify results before proceeding
4. Save decisions to persistent memory

## Delegation Rules

- Reading 4+ files -> Delegate exploration
- Touching 2+ files -> Use one writer + review
- Commits/PRs -> Fresh review required
- Security changes -> Additional approval gate

## Memory

Use persistent memory:
- Save architectural decisions
- Record bug fixes with root cause
- Document patterns and conventions
- Capture gotchas and edge cases
"""
