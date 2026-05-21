"""Agent installer - generates configuration files for 13+ AI coding agents.

Provides automated detection and configuration generation for popular AI coding tools.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar


class AgentTarget(StrEnum):
    """Supported AI coding agents."""

    CLAUDE_CODE = "claude-code"
    OPENCODE = "opencode"
    KILO_CODE = "kilo-code"
    GEMINI_CLI = "gemini-cli"
    CURSOR = "cursor"
    VSCODE_COPILOT = "vscode-copilot"
    CODEX = "codex"
    WINDSURF = "windsurf"
    ANTIGRAVITY = "antigravity"
    KIMI_CODE = "kimi-code"
    KIRO_IDE = "kiro-ide"
    QWEN_CODE = "qwen-code"
    OPENCLAW = "openclaw"
    PI = "pi"


@dataclass
class AgentConfig:
    """Configuration for a specific agent."""

    target: AgentTarget
    config_path: Path
    instructions_path: Path | None
    mcp_config: dict[str, Any] | None
    permissions: list[str] | None


class AgentInstaller:
    """Installs OpenContext integration for various AI agents.

    Generates config files, MCP server configs, and instruction files
    for each supported agent.
    """

    SUPPORTED_AGENTS: ClassVar[list[AgentTarget]] = list(AgentTarget)

    @staticmethod
    def _get_agent_dir(target: AgentTarget) -> Path:
        """Get the config directory for a given agent target."""

        home = Path.home()
        dirs = {
            AgentTarget.CLAUDE_CODE: home / ".claude",
            AgentTarget.OPENCODE: home / ".config" / "opencode",
            AgentTarget.KILO_CODE: home / ".config" / "kilo",
            AgentTarget.GEMINI_CLI: home / ".gemini",
            AgentTarget.CURSOR: home / ".cursor",
            AgentTarget.CODEX: home / ".codex",
            AgentTarget.WINDSURF: home / ".windsurf",
            AgentTarget.KIMI_CODE: home / ".kimi",
            AgentTarget.KIRO_IDE: home / ".kiro",
            AgentTarget.QWEN_CODE: home / ".qwen",
            AgentTarget.OPENCLAW: home / ".openclaw",
            AgentTarget.PI: home / ".pi",
            AgentTarget.ANTIGRAVITY: home / ".antigravity",
            AgentTarget.VSCODE_COPILOT: home / ".vscode",
        }
        return dirs.get(target, home / f".{target.value}")

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.opencontext_dir = self.project_root / ".opencontext"
        self.storage_dir = self.opencontext_dir / "agent-configs"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def detect_installed_agents(self) -> list[AgentTarget]:
        """Auto-detect which agents are installed on the system."""

        detected: list[AgentTarget] = []

        for agent in AgentTarget:
            path = self._get_agent_dir(agent)
            if path.exists():
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

        results: list[dict[str, Any]] = []
        for target in targets:
            result = self._install_agent(target, location)
            results.append(result)

        return {
            "status": "installed",
            "location": location,
            "project": str(self.project_root),
            "agents_configured": len(results),
            "results": results,
        }

    def _install_agent(self, target: AgentTarget, location: str) -> dict[str, Any]:
        """Install configuration for a single agent."""

        config_generators: dict[AgentTarget, str] = {
            AgentTarget.CLAUDE_CODE: "claude",
            AgentTarget.OPENCODE: "opencode",
            AgentTarget.CURSOR: "cursor",
            AgentTarget.CODEX: "codex",
            AgentTarget.WINDSURF: "windsurf",
            AgentTarget.VSCODE_COPILOT: "vscode",
            AgentTarget.GEMINI_CLI: "gemini",
            AgentTarget.KILO_CODE: "opencode",
            AgentTarget.KIMI_CODE: "opencode",
            AgentTarget.KIRO_IDE: "cursor",
            AgentTarget.QWEN_CODE: "codex",
            AgentTarget.OPENCLAW: "claude",
            AgentTarget.PI: "codex",
            AgentTarget.ANTIGRAVITY: "gemini",
        }

        gen_name = config_generators.get(target)
        if gen_name is None:
            return {
                "agent": target.value,
                "status": "skipped",
                "reason": f"Configuration generator not yet available for '{target.value}'",
            }

        generator = getattr(self, f"_gen_{gen_name}_config", None)
        if generator is None:
            return {
                "agent": target.value,
                "status": "skipped",
                "reason": f"Generator '{gen_name}' not implemented",
            }

        return generator(location, target)

    def _gen_claude_config(
        self, location: str, target: AgentTarget = AgentTarget.CLAUDE_CODE
    ) -> dict[str, Any]:
        """Generate Claude Code / OpenClaw configuration."""

        agent_dir = self._get_agent_dir(target)
        agent_dir.mkdir(parents=True, exist_ok=True)

        agent_name = target.value
        mcp_label = "opencontext"

        # MCP server config
        mcp_config = {
            "mcpServers": {
                mcp_label: {
                    "type": "stdio",
                    "command": "opencontext",
                    "args": ["serve", "--mcp"],
                }
            }
        }

        mcp_path = agent_dir / "mcp.json"
        self._merge_json_config(mcp_path, mcp_config)

        # Instructions file (CLAUDE.md or AGENTS.md depending on agent)
        instructions = self._build_agent_instructions("claude")
        instr_name = "CLAUDE.md" if target == AgentTarget.CLAUDE_CODE else "AGENTS.md"
        instructions_path = agent_dir / instr_name
        instructions_path.write_text(instructions, encoding="utf-8")

        files_created = [str(mcp_path), str(instructions_path)]

        # Permissions for auto-allow (Claude-specific)
        if target == AgentTarget.CLAUDE_CODE:
            permissions_path = agent_dir / "settings.json"
            permissions = {
                "permissions": {
                    "allow": [
                        "mcp__opencontext__opencontext_search",
                        "mcp__opencontext__opencontext_context",
                        "mcp__opencontext__opencontext_callers",
                        "mcp__opencontext__opencontext_callees",
                        "mcp__opencontext__opencontext_impact",
                        "mcp__opencontext__opencontext_node",
                        "mcp__opencontext__opencontext_files",
                        "mcp__opencontext__opencontext_status",
                    ]
                }
            }
            self._merge_json_config(permissions_path, permissions)
            files_created.append(str(permissions_path))

        return {
            "agent": agent_name,
            "status": "configured",
            "files": files_created,
        }

    def _gen_opencode_config(
        self, location: str, target: AgentTarget = AgentTarget.OPENCODE
    ) -> dict[str, Any]:
        """Generate OpenCode / Kilo Code / Kimi Code configuration."""

        config_dir = self._get_agent_dir(target)
        config_dir.mkdir(parents=True, exist_ok=True)

        agent_name = target.value

        # MCP config
        mcp_config = {
            "mcpServers": {
                "opencontext": {
                    "type": "stdio",
                    "command": "opencontext",
                    "args": ["serve", "--mcp"],
                }
            }
        }

        mcp_path = config_dir / "mcp.json"
        self._merge_json_config(mcp_path, mcp_config)

        files_created = [str(mcp_path)]

        # Agent profile for SDD orchestrator (OpenCode-specific)
        if target == AgentTarget.OPENCODE:
            profile_dir = config_dir / "agents"
            profile_dir.mkdir(parents=True, exist_ok=True)

            sdd_profile = {
                "name": "sdd-orchestrator",
                "description": "OpenContext SDD orchestrator with knowledge graph",
                "system_prompt": self._build_orchestrator_prompt(),
                "tools": ["mcp__opencontext__*"],
            }

            profile_path = profile_dir / "sdd-orchestrator.json"
            profile_path.write_text(json.dumps(sdd_profile, indent=2), encoding="utf-8")
            files_created.append(str(profile_path))

        # Instructions
        instr_type = "opencode"
        instr_path = config_dir / "AGENTS.md"
        instr_path.write_text(self._build_agent_instructions(instr_type), encoding="utf-8")
        files_created.append(str(instr_path))

        return {
            "agent": agent_name,
            "status": "configured",
            "files": files_created,
        }

    def _gen_cursor_config(
        self, location: str, target: AgentTarget = AgentTarget.CURSOR
    ) -> dict[str, Any]:
        """Generate Cursor / Kiro IDE configuration."""

        agent_dir = self._get_agent_dir(target)
        agent_dir.mkdir(parents=True, exist_ok=True)

        agent_name = target.value

        # Rules file
        rules_dir = agent_dir / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)

        rules = self._build_agent_instructions("cursor")
        rules_path = rules_dir / "opencontext.mdc"
        rules_path.write_text(rules, encoding="utf-8")

        return {
            "agent": agent_name,
            "status": "configured",
            "files": [str(rules_path)],
        }

    def _gen_codex_config(
        self, location: str, target: AgentTarget = AgentTarget.CODEX
    ) -> dict[str, Any]:
        """Generate Codex CLI / Qwen Code / Pi configuration."""

        agent_dir = self._get_agent_dir(target)
        agent_dir.mkdir(parents=True, exist_ok=True)

        agent_name = target.value

        agents_md = agent_dir / "AGENTS.md"
        instr_type = "codex" if target == AgentTarget.CODEX else "generic"
        agents_md.write_text(self._build_agent_instructions(instr_type), encoding="utf-8")

        return {
            "agent": agent_name,
            "status": "configured",
            "files": [str(agents_md)],
        }

    def _gen_windsurf_config(
        self, location: str, target: AgentTarget = AgentTarget.WINDSURF
    ) -> dict[str, Any]:
        """Generate Windsurf configuration."""

        windsurf_dir = self._get_agent_dir(target)
        windsurf_dir.mkdir(parents=True, exist_ok=True)

        workflows_dir = windsurf_dir / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)

        workflow = self._build_windsurf_workflow()
        workflow_path = workflows_dir / "opencontext.md"
        workflow_path.write_text(workflow, encoding="utf-8")

        return {
            "agent": target.value,
            "status": "configured",
            "files": [str(workflow_path)],
        }

    def _gen_vscode_config(
        self, location: str, target: AgentTarget = AgentTarget.VSCODE_COPILOT
    ) -> dict[str, Any]:
        """Generate VS Code Copilot configuration."""

        vscode_dir = self._get_agent_dir(target)
        vscode_dir.mkdir(parents=True, exist_ok=True)

        settings = {
            "github.copilot.advanced": {
                "opencontext.enabled": True,
                "opencontext.mcpServer": "opencontext",
            }
        }

        settings_path = vscode_dir / "settings.json"
        self._merge_json_config(settings_path, settings)

        return {
            "agent": target.value,
            "status": "configured",
            "files": [str(settings_path)],
        }

    def _gen_gemini_config(
        self, location: str, target: AgentTarget = AgentTarget.GEMINI_CLI
    ) -> dict[str, Any]:
        """Generate Gemini CLI / Antigravity configuration."""

        agent_dir = self._get_agent_dir(target)
        agent_dir.mkdir(parents=True, exist_ok=True)

        agents_dir = agent_dir / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        instr_type = "gemini" if target == AgentTarget.GEMINI_CLI else "generic"
        agent_config = {
            "name": "opencontext",
            "description": "OpenContext knowledge graph integration",
            "instructions": self._build_agent_instructions(instr_type),
        }

        agent_path = agents_dir / "opencontext.json"
        agent_path.write_text(json.dumps(agent_config, indent=2), encoding="utf-8")

        return {
            "agent": target.value,
            "status": "configured",
            "files": [str(agent_path)],
        }

    def _merge_json_config(self, path: Path, new_config: dict[str, Any]) -> None:
        """Merge new config into existing JSON file."""

        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = {}

        # Deep merge
        merged = self._deep_merge(existing, new_config)
        path.write_text(json.dumps(merged, indent=2), encoding="utf-8")

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

    def _build_agent_instructions(self, agent_type: str) -> str:
        """Build agent-specific instructions."""

        # CLI reference shared across all agents
        cli_ref = """### OpenContext CLI Reference

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
| | `opencontext onboard .` | Full project setup |
|"""

        # Agent-specific prefix
        if agent_type == "claude":
            prefix = """# OpenContext Integration

OpenContext provides a semantic knowledge graph, health checks, plugin ecosystem,
and SDD orchestration for this project. Use the MCP tools directly.

"""
        elif agent_type == "opencode":
            prefix = """# OpenContext Integration

OpenContext provides a semantic knowledge graph, health checks, plugin ecosystem,
and SDD orchestration. The SDD orchestrator agent profile is installed.

"""
        elif agent_type == "cursor":
            prefix = """---
description: OpenContext integration for code exploration and health
globs: 
---
# OpenContext Integration

OpenContext provides a semantic knowledge graph, health checks, plugin ecosystem,
and SDD orchestration for this project.

"""
        elif agent_type == "codex":
            prefix = """# OpenContext Integration for Codex CLI

OpenContext provides a semantic knowledge graph for code exploration,
health checks, plugin ecosystem, and self-update capabilities.

"""
        elif agent_type == "gemini":
            prefix = """# OpenContext Integration for Gemini CLI

OpenContext provides code exploration, health checks, and plugin management.

"""
        else:
            prefix = """# OpenContext Integration

OpenContext provides a semantic knowledge graph, health checks, plugin ecosystem,
and SDD orchestration for this project.

"""

        kg_section = """## Knowledge Graph (MCP Tools)

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

        health_section = """## Health & Maintenance

- Run `opencontext verify` to check all components are working
- Run `opencontext update` to check for OpenContext updates
- Run `opencontext upgrade` to install the latest version
- Run `opencontext plugin update` to update all plugins
- Run `opencontext config backup` before risky configuration changes
"""

        sdd_section = """## SDD Workflow

This project supports Spec-Driven Development.

- Run `opencontext init` to initialize SDD if not done
- Use `/sdd-new <change>` in OpenCode to start a new change
- The orchestrator handles: explore → propose → spec → design → tasks → apply → verify → archive
"""

        security = """## Security

- All tool executions require approval by default
- External providers are disabled in secure mode
- Context redaction is applied automatically
"""

        return prefix + kg_section + cli_ref + "\n" + health_section + sdd_section + security

    def _build_orchestrator_prompt(self) -> str:
        """Build the SDD orchestrator system prompt."""

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

- Reading 4+ files → Delegate exploration
- Touching 2+ files → Use one writer + review
- Commits/PRs → Fresh review required
- Security changes → Additional approval gate

## Memory

Use Engram-style persistent memory:
- Save architectural decisions
- Record bug fixes with root cause
- Document patterns and conventions
- Capture gotchas and edge cases
"""

    def _build_windsurf_workflow(self) -> str:
        """Build Windsurf workflow file."""

        return """# OpenContext Workflow for Windsurf

## Plan Mode

1. Use `opencontext_status` to check if knowledge graph is initialized
2. If not initialized, run `opencontext init` first
3. Use `opencontext_context` to gather relevant code for the task
4. Use `opencontext_impact` to understand change scope

## Code Mode

1. Reference the knowledge graph for symbol locations
2. Use `opencontext_search` to find specific functions/classes
3. Use `opencontext_callers`/`opencontext_callees` to understand relationships
4. Verify changes with `opencontext_impact` before committing

## Rules

- Always check impact before refactoring
- Use context tool instead of manual file scanning
- Save important decisions to memory
"""

    def uninstall(self, targets: list[AgentTarget] | None = None) -> dict[str, Any]:
        """Remove OpenContext configuration from agents."""

        # This would remove the configs we added
        return {
            "status": "not_implemented",
            "message": "Uninstall requires tracking what was installed",
        }
