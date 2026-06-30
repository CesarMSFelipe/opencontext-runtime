"""Configure existing AI coding agents with the right files and MCP shape.

``Configurator`` is the single entry point. For each requested agent it:
- writes the MCP server entry in the agent's native shape,
- injects a managed instructions block into the agent's rules file
  (AGENTS.md / CLAUDE.md / GEMINI.md / QWEN.md, project- or home-scoped),
- writes any agent-specific extras (claude permissions, personas, ignores),

all through the safe-merge primitives so user-owned content is never clobbered.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from opencontext_core.agents.template_renderer import (
    RENDER_SCOPE_LOCAL_REASON,
    render_agent_instructions,
)
from opencontext_core.configurator import constants
from opencontext_core.configurator.adapter import Adapter, get_adapter, iter_adapters
from opencontext_core.configurator.backup import BackupStore, plan_actions
from opencontext_core.configurator.filemerge import (
    inject_managed_lines,
    inject_managed_section,
    write_text_atomic,
)
from opencontext_core.configurator.mcp_strategy import (
    McpShape,
    plan_mcp_servers,
    remove_mcp_server,
)

if TYPE_CHECKING:
    from opencontext_core.personas import Persona

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
        self,
        agents: list[str],
        scope: str = "local",
        *,
        dry_run: bool = False,
        project_only: bool = False,
    ) -> dict[str, Any]:
        """Configure ``agents`` and return a structured report.

        When ``dry_run`` is true, nothing is written: each agent's result
        describes the planned changes (which files, created vs modified) instead.

        ``scope`` is advisory and echoed in the report; it does NOT move files
        between the project and the home dir. Each file's location is determined
        per-agent by the adapter: AGENTS.md-honoring agents get project-root
        instructions, while MCP config, personas, and CLAUDE.md/GEMINI.md agents
        always write to the agent's own config dir under home.

        When ``project_only`` is true, ONLY repo-local files are written (the
        project-root ``.mcp.json``); the agent's home-dir config (home MCP,
        CLAUDE.md, settings) and the home backup are skipped. This is what a
        ``--scope workspace`` install uses so it never touches ``$HOME``.
        """

        results = [
            self.configure_one(agent_id, scope, dry_run=dry_run, project_only=project_only)
            for agent_id in agents
        ]
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
        self,
        agent_id: str,
        scope: str = "local",
        *,
        dry_run: bool = False,
        project_only: bool = False,
    ) -> dict[str, Any]:
        """Configure a single agent; returns its per-agent result entry."""

        adapter = get_adapter(agent_id)
        plan = self._plan(adapter)
        targets = [path for path, content in plan if content is not None]

        if dry_run:
            planned = plan_actions(targets)
            return {
                "agent": agent_id,
                "status": "planned",
                "plan": planned,
                **self._classified_file_report([entry["path"] for entry in planned], scope),
            }

        # project_only: write nothing under $HOME — no home backup. Write every
        # planned file that lives under the project root (repo .mcp.json, project
        # commands, agents, delegates) and skip home-dir files (home MCP, CLAUDE.md,
        # settings). Used by --scope workspace installs.
        if project_only:
            files = self._write_project_local_only(adapter)
            return {
                "agent": agent_id,
                "status": "configured",
                "files": files,
                **self._classified_file_report(files, scope),
                "backup_id": None,
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
            **self._classified_file_report(files, scope),
            "backup_id": backup.id if backup is not None else None,
        }

    def _classified_file_report(self, files: list[str], scope: str) -> dict[str, Any]:
        """Classify writes so `--scope local` cannot hide home/global changes."""
        root = self.project_root.resolve()
        local: list[str] = []
        global_: list[str] = []
        for file in files:
            path = Path(file)
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if root == resolved or root in resolved.parents:
                local.append(file)
            else:
                global_.append(file)
        report: dict[str, Any] = {
            "local_files_written": local,
            "global_files_written": global_,
        }
        if scope == "local" and global_:
            # Spec 8.9: the --scope=local decision is Host-Constrained Local
            # and the JSON envelope MUST explain every global write. The
            # renderer owns the canonical wording so the docs and the JSON
            # cannot drift apart.
            report["global_write_reason"] = RENDER_SCOPE_LOCAL_REASON
        return report

    def _write_project_local_only(self, adapter: Adapter) -> list[str]:
        """Write every planned file under the project root; touch nothing under $HOME."""
        root = self.project_root.resolve()
        files: list[str] = []
        for path, content in self._plan(adapter):
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if root != resolved and root not in resolved.parents:
                continue  # home-dir file — skip in project-only mode
            if content is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                write_text_atomic(path, content)
            files.append(str(path))
        return files

    # ------------------------------------------------------------------

    def deconfigure(
        self, agents: list[str], scope: str = "local", *, dry_run: bool = False
    ) -> dict[str, Any]:
        """Remove OpenContext's managed config from ``agents``, leaving user content.

        The inverse of :meth:`configure`: strips the managed instructions block and
        the ``opencontext`` MCP entry (and agent-specific extras) without touching
        anything the developer authored.

        ``scope`` is advisory (see :meth:`configure`): removal targets are the same
        adapter-determined paths regardless of scope.
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
        project_mcp_name = constants.project_mcp_filename(adapter.agent_id)
        project_mcp_path = self.project_root / project_mcp_name if project_mcp_name else None
        if project_mcp_path is not None:
            candidates.append(project_mcp_path)
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
            # 2. Remove our MCP server entry in the agent's native shape. If the
            #    file is now empty (it only ever held our entry), unlink it so
            #    install leaves no `{}` orphan — mirrors the instructions unlink.
            if remove_mcp_server(
                adapter.mcp_config_path, constants.MCP_LABEL, shape=adapter.mcp_shape
            ):
                changed.append(str(adapter.mcp_config_path))
                _unlink_if_empty_mcp(adapter.mcp_config_path, adapter.mcp_shape)
            # 2b. Remove the project-scoped MCP entry (e.g. repo-root .mcp.json).
            if project_mcp_path is not None and remove_mcp_server(
                project_mcp_path, constants.MCP_LABEL, shape=adapter.mcp_shape
            ):
                changed.append(str(project_mcp_path))
                _unlink_if_empty_mcp(project_mcp_path, adapter.mcp_shape)
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
                        # Drop an emptied permissions block, then unlink a
                        # settings.json that now holds nothing — install created it
                        # for our allow-list, so a leftover {"permissions": {}} is
                        # an orphan. User keys (theme, other perms) keep the file.
                        if isinstance(data.get("permissions"), dict) and not data["permissions"]:
                            data.pop("permissions", None)
                        if not data:
                            path.unlink()
                        else:
                            write_text_atomic(path, json.dumps(data, indent=2) + "\n")
                        changed.append(str(path))
        if adapter.agent_id == "opencode":
            path = adapter.config_dir / "agents" / "sdd-orchestrator.json"
            if path.exists():
                path.unlink()
                changed.append(str(path))
        subdir = constants.global_agents_subdir(adapter.agent_id)
        if subdir:
            from opencontext_core.personas import public_personas

            agents_dir = adapter.config_dir / subdir
            for persona in public_personas():
                path = agents_dir / f"{persona.id}.md"
                if path.exists():
                    path.unlink()
                    changed.append(str(path))
            # Remove the global agents dir if our personas were its only contents —
            # install created it, so an empty leftover is an orphan. rmdir only
            # succeeds when empty, so any user-authored file always keeps it.
            try:
                agents_dir.rmdir()
            except OSError:
                pass
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
            from opencontext_core.personas import public_personas

            persona_dir = self.project_root / persona_rel
            for persona in public_personas():
                path = persona_dir / f"{persona.id}.md"
                if path.exists():
                    path.unlink()  # whole file we created
                    changed.append(str(path))
        changed.extend(self._remove_hidden_delegation_personas(adapter))
        return changed

    def _plan(self, adapter: Adapter) -> list[PlanEntry]:
        """Compute every file this agent would touch and its merged content.

        The plan drives the dry-run report and the pre-change backup snapshot;
        the matching ``_write_*`` methods perform the real writes during apply.
        """

        plan: list[PlanEntry] = []
        plan.append(self._plan_mcp(adapter))
        project_mcp = self._plan_project_mcp(adapter)
        if project_mcp is not None:
            plan.append(project_mcp)
        plan.append(self._plan_instructions(adapter))
        plan.extend(self._plan_extras(adapter))
        return plan

    def _write_mcp(self, adapter: Adapter) -> list[str]:
        files: list[str] = []
        for entry in (self._plan_mcp(adapter), self._plan_project_mcp(adapter)):
            if entry is None:
                continue
            path, content = entry
            if content is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                write_text_atomic(path, content)
            files.append(str(path))
        return files

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

    def _plan_project_mcp(self, adapter: Adapter) -> PlanEntry | None:
        """Plan a repo-root ``.mcp.json`` for agents that read one (e.g. Claude Code).

        Returns ``None`` for agents without a project-scoped MCP file. The home
        MCP entry alone does not enable the server per-repo, so this is what lets a
        single checkout pick up the OpenContext tools.
        """
        filename = constants.project_mcp_filename(adapter.agent_id)
        if filename is None:
            return None
        servers = {constants.MCP_LABEL: dict(constants.MCP_SERVER_ENTRY)}
        return plan_mcp_servers(self.project_root / filename, servers, shape=adapter.mcp_shape)

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
        if constants.global_agents_subdir(adapter.agent_id):
            entries.extend(self._plan_global_personas(adapter))
        if constants.ignore_filename(adapter.agent_id):
            entries.append(self._plan_ignore(adapter))
        if constants.command_dir(adapter.agent_id):
            entries.extend(self._plan_commands(adapter))
        if constants.persona_dir(adapter.agent_id):
            entries.extend(self._plan_personas(adapter))
        if constants.hidden_delegation_dir(adapter.agent_id):
            entries.extend(self._plan_hidden_delegation_personas(adapter))
        return entries

    def _plan_hidden_delegation_personas(self, adapter: Adapter) -> list[PlanEntry]:
        """Plan hidden delegation persona files under a hidden subdirectory."""
        from opencontext_core.personas import hidden_delegation_personas

        rel = constants.hidden_delegation_dir(adapter.agent_id)
        if rel is None:
            return []

        root = self.project_root / rel
        entries: list[PlanEntry] = []

        for persona in hidden_delegation_personas():
            path = root / f"{persona.id}.md"
            content = _render_persona(persona)
            entries.append((path, _content_if_changed(path, content)))

        return entries

    def _remove_hidden_delegation_personas(self, adapter: Adapter) -> list[str]:
        """Remove hidden delegation persona files."""
        rel = constants.hidden_delegation_dir(adapter.agent_id)
        if rel is None:
            return []

        root = self.project_root / rel
        changed: list[str] = []

        if root.exists():
            for path in root.glob("oc-*.md"):
                path.unlink()
                changed.append(str(path))
            try:
                root.rmdir()
            except OSError:
                pass

        return changed

    def _plan_personas(self, adapter: Adapter) -> list[PlanEntry]:
        """Plan the agent's persona/subagent files (OC Orchestrator/Professor/Reviewer)."""
        from opencontext_core.personas import public_personas

        persona_dir = self.project_root / str(constants.persona_dir(adapter.agent_id))
        entries: list[PlanEntry] = []
        for persona in public_personas():
            path = persona_dir / f"{persona.id}.md"
            content = _render_persona(persona)
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
        from opencontext_core.personas import public_personas

        subdir = constants.global_agents_subdir(adapter.agent_id)
        agents_dir = adapter.config_dir / str(subdir)
        entries: list[PlanEntry] = []
        for persona in public_personas():
            path = agents_dir / f"{persona.id}.md"
            content = _render_persona(persona)
            entries.append((path, _content_if_changed(path, content)))
        return entries


def _mcp_config_is_empty(path: Path, shape: McpShape) -> bool:
    """True when an MCP config holds no remaining configuration of its declared shape.

    Only consulted right after our own server entry was removed, so an empty result
    means OpenContext created the file (or it has nothing left worth keeping) and it
    is safe to unlink — the same "file held only our block" rule used for CLAUDE.md.
    A file with any other server or top-level key is reported non-empty and kept.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.strip():
        return True
    if shape in (McpShape.JSON_MCP_SERVERS, McpShape.JSON_SERVERS):
        try:
            return bool(json.loads(text) == {})
        except json.JSONDecodeError:
            return False
    if shape is McpShape.YAML_MCP_SERVERS:
        import yaml

        try:
            return yaml.safe_load(text) in (None, {})
        except yaml.YAMLError:
            return False
    if shape is McpShape.TOML_MCP_SERVERS:
        import tomllib

        try:
            return tomllib.loads(text) == {}
        except tomllib.TOMLDecodeError:
            return False
    return False


def _unlink_if_empty_mcp(path: Path, shape: McpShape) -> None:
    """Unlink an MCP config file that holds nothing after our server was removed."""
    if path.exists() and _mcp_config_is_empty(path, shape):
        try:
            path.unlink()
        except OSError:
            pass


def _content_if_changed(path: Path, content: str) -> str | None:
    """Return ``content`` unless ``path`` already holds it (a no-op write)."""

    if path.exists():
        try:
            if path.read_text(encoding="utf-8") == content:
                return None
        except OSError:
            pass
    return content


def _render_persona(persona: Persona) -> str:
    """Render a persona to its native subagent file.

    Emits a ``tools:`` frontmatter line from the persona's allow-list so the KG
    preference is enforced by the host (KG/memory MCP tools + Read/Edit/Write per
    phase, never native Grep/Glob), not just stated in prose.
    """

    lines = [f"name: {persona.name}", f"description: {persona.description}"]
    if persona.tools:
        lines.append("tools:")
        lines.extend(f"  {tool}: true" for tool in persona.tools)
    frontmatter = "\n".join(lines)
    return f"---\n{frontmatter}\n---\n\n{persona.system_prompt}\n"


# ----------------------------------------------------------------------
# Default content
# ----------------------------------------------------------------------

# The managed instructions body is now produced by the consolidated renderer
# (``opencontext_core.agents.template_renderer``) so doc content can be
# unit-tested, so per-host overrides have a single place to slot in, and so
# the spec-required topics (opencontext_run, memory, quality, session,
# workflow/profile explain, config doctor, trace/status, symbol edit, OC Flow
# vs SDD, TDD mode, memory/Engram) cannot drift back into partial coverage.
# ``_default_instructions`` is kept as the Configurator's entry point so
# existing tests and ``instructions_builder`` overrides keep working.


def _default_instructions(agent_id: str) -> str:
    """Build the managed instructions body for an agent.

    Delegates to ``opencontext_core.agents.template_renderer`` so the doc
    body is the consolidated, spec-covered set of topics rather than the
    older inline set. ``agent_id`` is kept in the signature for any future
    per-host override; the renderer is pure.
    """

    return render_agent_instructions(agent_id)
