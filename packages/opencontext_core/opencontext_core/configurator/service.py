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
from opencontext_core.configurator.backup import BackupStore, plan_actions
from opencontext_core.configurator.filemerge import (
    inject_managed_lines,
    inject_managed_section,
    write_text_atomic,
)
from opencontext_core.configurator.mcp_strategy import (
    plan_mcp_servers,
    remove_mcp_server,
)

InstructionsBuilder = Callable[[str], str]

# A planned write: the target file and the exact content it would receive, or
# ``None`` when the file is already current (the write would be a no-op).
PlanEntry = tuple[Path, str | None]


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

    def configure(
        self, agents: list[str], scope: str = "local", *, dry_run: bool = False
    ) -> dict[str, Any]:
        """Configure ``agents`` and return a structured report.

        When ``dry_run`` is true, nothing is written: each agent's result
        describes the planned changes (which files, created vs modified) instead.
        """

        results = [self.configure_one(agent_id, scope, dry_run=dry_run) for agent_id in agents]
        status_key = "planned" if dry_run else "configured"
        configured = sum(1 for r in results if r["status"] == status_key)
        return {
            "status": "planned" if dry_run else "configured",
            "scope": scope,
            "project": str(self.project_root),
            "agents_configured": configured,
            "dry_run": dry_run,
            "results": results,
        }

    def configure_one(
        self, agent_id: str, scope: str = "local", *, dry_run: bool = False
    ) -> dict[str, Any]:
        """Configure a single agent; returns its per-agent result entry."""

        adapter = get_adapter(agent_id)
        plan = self._plan(adapter)
        targets = [path for path, content in plan if content is not None]

        if dry_run:
            return {
                "agent": agent_id,
                "status": "planned",
                "plan": plan_actions(targets),
            }

        backup = BackupStore().create([agent_id], targets, source="configure")
        try:
            files = self._write_mcp(adapter)
            files.append(self._write_instructions(adapter))
            files.extend(self._write_extras(adapter))
        except Exception:
            if backup is not None:
                BackupStore().restore(backup.id)
            raise

        return {
            "agent": agent_id,
            "status": "configured",
            "files": files,
            "backup_id": backup.id if backup is not None else None,
        }

    # ------------------------------------------------------------------

    def deconfigure(
        self, agents: list[str], scope: str = "local", *, dry_run: bool = False
    ) -> dict[str, Any]:
        """Remove OpenContext's managed config from ``agents``, leaving user content.

        The inverse of :meth:`configure`: strips the managed instructions block and
        the ``opencontext`` MCP entry (and agent-specific extras) without touching
        anything the developer authored.
        """

        results = [self.deconfigure_one(agent_id, scope, dry_run=dry_run) for agent_id in agents]
        status_key = "planned" if dry_run else "removed"
        removed = sum(1 for r in results if r["status"] == status_key)
        return {
            "status": "planned" if dry_run else "removed",
            "scope": scope,
            "project": str(self.project_root),
            "agents_removed": removed,
            "dry_run": dry_run,
            "results": results,
        }

    def deconfigure_one(
        self, agent_id: str, scope: str = "local", *, dry_run: bool = False
    ) -> dict[str, Any]:
        """Remove a single agent's managed OpenContext config; return its result."""

        adapter = get_adapter(agent_id)
        instructions_path = adapter.instructions_path(self.project_root)
        candidates = [adapter.mcp_config_path, instructions_path]
        ignore_name = constants.ignore_filename(adapter.agent_id)
        if ignore_name:
            candidates.append(self.project_root / ignore_name)
        touched = [p for p in candidates if p.exists()]

        if dry_run:
            return {"agent": agent_id, "status": "planned", "plan": plan_actions(touched)}

        backup = BackupStore().create([agent_id], touched, source="uninstall")
        try:
            changed: list[str] = []
            # 1. Strip our managed instructions block (empty content removes it).
            if instructions_path.exists():
                existing = instructions_path.read_text(encoding="utf-8")
                stripped = inject_managed_section(existing, "instructions", "")
                if stripped != existing:
                    if stripped.strip():
                        write_text_atomic(instructions_path, stripped)
                    else:
                        instructions_path.unlink()  # file held only our block
                    changed.append(str(instructions_path))
            # 2. Remove our MCP server entry in the agent's native shape.
            if remove_mcp_server(
                adapter.mcp_config_path, constants.MCP_LABEL, shape=adapter.mcp_shape
            ):
                changed.append(str(adapter.mcp_config_path))
            # 3. Reverse agent-specific extras.
            changed.extend(self._remove_extras(adapter))
        except Exception:
            if backup is not None:
                BackupStore().restore(backup.id)
            raise

        return {
            "agent": agent_id,
            "status": "removed",
            "files": changed,
            "backup_id": backup.id if backup is not None else None,
        }

    def _remove_extras(self, adapter: Adapter) -> list[str]:
        """Reverse the agent-specific extras written by :meth:`configure_one`."""
        changed: list[str] = []
        if adapter.agent_id == "claude-code":
            path = adapter.config_dir / "settings.json"
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    data = {}
                allow = data.get("permissions", {}).get("allow")
                if isinstance(allow, list):
                    kept = [t for t in allow if t not in set(constants.ALLOWED_TOOLS)]
                    if kept != allow:
                        if kept:
                            data["permissions"]["allow"] = kept
                        else:
                            data["permissions"].pop("allow", None)
                        write_text_atomic(path, json.dumps(data, indent=2) + "\n")
                        changed.append(str(path))
        if adapter.agent_id == "opencode":
            path = adapter.config_dir / "agents" / "sdd-orchestrator.json"
            if path.exists():
                path.unlink()
                changed.append(str(path))
        subdir = constants.global_agents_subdir(adapter.agent_id)
        if subdir:
            from opencontext_core.personas import PERSONAS

            for persona in PERSONAS:
                path = adapter.config_dir / subdir / f"{persona.id}.md"
                if path.exists():
                    path.unlink()
                    changed.append(str(path))
        ignore_name = constants.ignore_filename(adapter.agent_id)
        if ignore_name:
            path = self.project_root / ignore_name
            if path.exists():
                existing = path.read_text(encoding="utf-8")
                stripped = inject_managed_lines(existing, "ignore", [])
                if stripped != existing:
                    if stripped.strip():
                        write_text_atomic(path, stripped)
                    else:
                        path.unlink()  # file held only our block
                    changed.append(str(path))
        cmd_rel = constants.command_dir(adapter.agent_id)
        if cmd_rel:
            cmd_dir = self.project_root / cmd_rel
            for name, _desc, _body in constants.OPENCONTEXT_COMMANDS:
                path = cmd_dir / f"{name}.md"
                if path.exists():
                    path.unlink()  # whole file we created
                    changed.append(str(path))
        persona_rel = constants.persona_dir(adapter.agent_id)
        if persona_rel:
            from opencontext_core.personas import PERSONAS

            persona_dir = self.project_root / persona_rel
            for persona in PERSONAS:
                path = persona_dir / f"{persona.id}.md"
                if path.exists():
                    path.unlink()  # whole file we created
                    changed.append(str(path))
        return changed

    def _plan(self, adapter: Adapter) -> list[PlanEntry]:
        """Compute every file this agent would touch and its merged content.

        The plan drives the dry-run report and the pre-change backup snapshot;
        the matching ``_write_*`` methods perform the real writes during apply.
        """

        plan: list[PlanEntry] = []
        plan.append(self._plan_mcp(adapter))
        plan.append(self._plan_instructions(adapter))
        plan.extend(self._plan_extras(adapter))
        return plan

    def _write_mcp(self, adapter: Adapter) -> list[str]:
        path, content = self._plan_mcp(adapter)
        if content is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_text_atomic(path, content)
        return [str(path)]

    def _write_instructions(self, adapter: Adapter) -> str:
        path, content = self._plan_instructions(adapter)
        if content is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_text_atomic(path, content)
        return str(path)

    def _write_extras(self, adapter: Adapter) -> list[str]:
        files: list[str] = []
        for path, content in self._plan_extras(adapter):
            files.append(str(path))
            if content is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                write_text_atomic(path, content)
        return files

    def _plan_mcp(self, adapter: Adapter) -> PlanEntry:
        servers = {constants.MCP_LABEL: dict(constants.MCP_SERVER_ENTRY)}
        return plan_mcp_servers(adapter.mcp_config_path, servers, shape=adapter.mcp_shape)

    def _plan_instructions(self, adapter: Adapter) -> PlanEntry:
        path = adapter.instructions_path(self.project_root)
        content = self._build_instructions(adapter.agent_id)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        merged = inject_managed_section(existing, "instructions", content)
        return path, _content_if_changed(path, merged)

    def _plan_extras(self, adapter: Adapter) -> list[PlanEntry]:
        entries: list[PlanEntry] = []
        if adapter.agent_id == "claude-code":
            entries.append(self._plan_claude_permissions(adapter))
        if adapter.agent_id == "opencode":
            entries.append(self._plan_opencode_profile(adapter))
        if constants.global_agents_subdir(adapter.agent_id):
            entries.extend(self._plan_global_personas(adapter))
        if constants.ignore_filename(adapter.agent_id):
            entries.append(self._plan_ignore(adapter))
        if constants.command_dir(adapter.agent_id):
            entries.extend(self._plan_commands(adapter))
        if constants.persona_dir(adapter.agent_id):
            entries.extend(self._plan_personas(adapter))
        return entries

    def _plan_personas(self, adapter: Adapter) -> list[PlanEntry]:
        """Plan the agent's persona/subagent files (OC Orchestrator/Professor/Reviewer)."""
        from opencontext_core.personas import PERSONAS

        persona_dir = self.project_root / str(constants.persona_dir(adapter.agent_id))
        entries: list[PlanEntry] = []
        for persona in PERSONAS:
            path = persona_dir / f"{persona.id}.md"
            content = (
                f"---\nname: {persona.name}\ndescription: {persona.description}\n---\n\n"
                f"{persona.system_prompt}\n"
            )
            entries.append((path, _content_if_changed(path, content)))
        return entries

    def _plan_commands(self, adapter: Adapter) -> list[PlanEntry]:
        """Plan the agent's native slash-command files (whole files we own)."""
        cmd_dir = self.project_root / str(constants.command_dir(adapter.agent_id))
        entries: list[PlanEntry] = []
        for name, description, body in constants.OPENCONTEXT_COMMANDS:
            path = cmd_dir / f"{name}.md"
            content = f"---\ndescription: {description}\n---\n\n{body}\n"
            entries.append((path, _content_if_changed(path, content)))
        return entries

    def _plan_ignore(self, adapter: Adapter) -> PlanEntry:
        """Plan the agent's native ignore file: a managed block of secret/build
        patterns the agent should never read, merged with the user's own."""
        name = constants.ignore_filename(adapter.agent_id)
        path = self.project_root / str(name)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        merged = inject_managed_lines(existing, "ignore", list(constants.DEFAULT_IGNORE_PATTERNS))
        return path, _content_if_changed(path, merged)

    def _plan_claude_permissions(self, adapter: Adapter) -> PlanEntry:
        path = adapter.config_dir / "settings.json"
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = {}
        existing_allow = existing.get("permissions", {}).get("allow", [])
        allow = list(dict.fromkeys([*existing_allow, *constants.ALLOWED_TOOLS]))
        existing.setdefault("permissions", {})["allow"] = allow
        content = json.dumps(existing, indent=2) + "\n"
        return path, _content_if_changed(path, content)

    def _plan_global_personas(self, adapter: Adapter) -> list[PlanEntry]:
        """Write OC personas to the agent's global agents dir (e.g. ~/.config/opencode/agents/)."""
        from opencontext_core.personas import PERSONAS

        subdir = constants.global_agents_subdir(adapter.agent_id)
        agents_dir = adapter.config_dir / str(subdir)
        entries: list[PlanEntry] = []
        for persona in PERSONAS:
            path = agents_dir / f"{persona.id}.md"
            content = (
                f"---\nname: {persona.name}\ndescription: {persona.description}\n---\n\n"
                f"{persona.system_prompt}\n"
            )
            entries.append((path, _content_if_changed(path, content)))
        return entries

    def _plan_opencode_profile(self, adapter: Adapter) -> PlanEntry:
        profile = {
            "name": "sdd-orchestrator",
            "description": "OpenContext SDD orchestrator with knowledge graph",
            "system_prompt": _orchestrator_prompt(),
            "tools": ["mcp__opencontext__*"],
        }
        path = adapter.config_dir / "agents" / "sdd-orchestrator.json"
        content = json.dumps(profile, indent=2) + "\n"
        return path, _content_if_changed(path, content)


def _content_if_changed(path: Path, content: str) -> str | None:
    """Return ``content`` unless ``path`` already holds it (a no-op write)."""

    if path.exists():
        try:
            if path.read_text(encoding="utf-8") == content:
                return None
        except OSError:
            pass
    return content


# ----------------------------------------------------------------------
# Default content
# ----------------------------------------------------------------------

# Kept deliberately short: the agent can run `opencontext --help` for the full
# command set, so injecting a full CLI table into every session is wasted tokens.
_CLI_REFERENCE = """### OpenContext CLI

Run `opencontext --help` or `opencontext <command> --help` for the full command set.
Most-used: `index .` and `pack . --query "<task>"` (context), `verify` (health),
`install` (setup)."""

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
