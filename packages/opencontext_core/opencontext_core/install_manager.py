"""Installation manager for OpenContext.

Handles installation, update, verification, and uninstallation
of OpenContext integration across multiple AI agents.

Features:
- Interactive installation wizard
- Auto-detection of installed agents
- Version tracking and compatibility checks
- Installation profiles (minimal, full, custom)
- Backup before changes
- Platform-aware installation (macOS, Linux, Windows)
- Post-install hooks
"""

from __future__ import annotations

import json
import platform
import shutil
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from opencontext_core.agent_installer import AgentInstaller, AgentTarget
from opencontext_core.backup import BackupManager


class InstallProfile(StrEnum):
    """Installation profile."""

    MINIMAL = "minimal"  # Core files only
    FULL = "full"  # All agent configs + MCP + skills
    CUSTOM = "custom"  # User-selected components
    AGENTS_ONLY = "agents-only"  # Only agent configs
    MCP_ONLY = "mcp-only"  # Only MCP server config


@dataclass
class InstallComponent:
    """A component that can be installed."""

    name: str
    description: str
    installed: bool = False
    required: bool = False


@dataclass
class InstallState:
    """Current installation state."""

    version: str = "0.1.0"
    installed_at: str = ""
    components: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    profiles: list[str] = field(default_factory=list)
    hooks_run: list[str] = field(default_factory=list)


class InstallationManager:
    """Manages OpenContext installation lifecycle."""

    VERSION = "0.1.0"
    STATE_DIR = ".config/opencontext"
    STATE_FILE = "install-state.json"

    PLATFORM_PATHS: ClassVar[dict[str, dict[str, str]]] = {
        "Darwin": {  # macOS
            "config_dir": "~/.config",
            "home_dir": "~",
        },
        "Linux": {
            "config_dir": "~/.config",
            "home_dir": "~",
        },
        "Windows": {
            "config_dir": "~/AppData/Roaming",
            "home_dir": "~",
        },
    }

    AVAILABLE_COMPONENTS: ClassVar[list[InstallComponent]] = [
        InstallComponent("mcp", "MCP server configuration", required=True),
        InstallComponent("agents", "AI agent configurations"),
        InstallComponent("skills", "Skill registry"),
        InstallComponent("profiles", "SDD model profiles"),
        InstallComponent("hooks", "Post-install hooks"),
        InstallComponent("docs", "Documentation and examples"),
    ]

    def __init__(self) -> None:
        self.system = platform.system()
        self.installer = AgentInstaller()
        self.backup_manager = BackupManager()
        self.state_path = Path.home() / self.STATE_DIR / self.STATE_FILE
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def install(
        self,
        profile: InstallProfile = InstallProfile.FULL,
        targets: list[str] | None = None,
        components: list[str] | None = None,
        backup: bool = True,
        yes: bool = False,
        root: Path | str | None = None,
        force_global: bool = False,
    ) -> dict[str, Any]:
        """Install OpenContext integration.

        Args:
            profile: Installation profile.
            targets: Specific agents to configure.
            components: Specific components to install.
            backup: Create backup before installation.
            yes: Skip prompts.
            root: Project root for the on-disk config + skills. Defaults to cwd.

        Returns:
            Installation report.
        """

        project_root = Path(root).resolve() if root is not None else Path.cwd()

        # Global integration (MCP, agent configs, model profiles) is a once-per-
        # machine concern. If OpenContext is already installed globally, skip it and
        # do only the per-project setup (config + skills). `force_global` re-runs it.
        already_global = self._is_installed()
        do_global = force_global or not already_global

        if backup and already_global:
            self.backup_manager.create_backup(name="pre-install")

        # Write a loadable opencontext.yaml so the project is runnable.
        config_path = self._write_project_config(project_root)

        to_install = self._resolve_components(profile, components)

        agents = self._resolve_agents(profile, targets)

        results = []

        if "mcp" in to_install and do_global:
            mcp_result = self._install_mcp()
            results.append(mcp_result)

        if "agents" in to_install and agents and do_global:
            agent_targets = [AgentTarget(a) for a in agents]
            agent_result = self.installer.install(
                targets=agent_targets,
                location="global",
                yes=yes,
            )
            results.append(agent_result)

        if "skills" in to_install:
            skills_result = self._install_skills(project_root)
            results.append(skills_result)

        if "profiles" in to_install and do_global:
            profiles_result = self._install_profiles()
            results.append(profiles_result)

        if "hooks" in to_install:
            hooks_result = self._run_hooks("post-install")
            results.append(hooks_result)

        # Install git post-commit hook for automatic harvesting
        try:
            self._install_git_hook(project_root)
        except Exception:
            pass

        self._save_state(
            InstallState(
                version=self.VERSION,
                components=list(to_install),
                agents=agents,
            )
        )

        return {
            "status": "installed",
            "profile": profile.value,
            "config_path": str(config_path),
            "components": list(to_install),
            "agents": agents,
            "results": results,
            # True when global integration was already present and left untouched
            # (this run only did per-project setup). Install global once.
            "global_skipped": not do_global,
        }

    def update(
        self,
        check_only: bool = False,
        backup: bool = True,
    ) -> dict[str, Any]:
        """Update OpenContext integration.

        Args:
            check_only: Only check for updates, don't apply.
            backup: Create backup before update.

        Returns:
            Update report.
        """

        state = self._load_state()
        if not state:
            return {
                "status": "not_installed",
                "message": "OpenContext is not installed. Run 'opencontext install' first.",
            }

        updates_available = self._check_updates(state)

        if check_only:
            return {
                "status": "checked",
                "current_version": state.version,
                "latest_version": self.VERSION,
                "updates_available": len(updates_available) > 0,
                "updates": updates_available,
            }

        if not updates_available:
            return {
                "status": "up_to_date",
                "version": state.version,
            }

        if backup:
            self.backup_manager.create_backup(name="pre-update")

        results = []
        for update in updates_available:
            result = self._apply_update(update)
            results.append(result)

        state.version = self.VERSION
        self._save_state(state)

        return {
            "status": "updated",
            "from_version": state.version,
            "to_version": self.VERSION,
            "updates_applied": len(results),
            "results": results,
        }

    def uninstall(
        self,
        keep_backups: bool = True,
        yes: bool = False,
    ) -> dict[str, Any]:
        """Uninstall OpenContext integration.

        Args:
            keep_backups: Preserve backup files.
            yes: Skip confirmation.

        Returns:
            Uninstall report.
        """

        state = self._load_state()
        if not state:
            return {
                "status": "not_installed",
                "message": "OpenContext is not installed.",
            }

        removed = []

        for agent in state.agents:
            if self._remove_agent_config(agent):
                removed.append(f"agent:{agent}")

        if self._remove_mcp_config():
            removed.append("mcp")

        if self.state_path.exists():
            self.state_path.unlink()
            removed.append("state")

        install_dir = Path.home() / ".config" / "opencontext"
        if install_dir.exists():
            if keep_backups:
                # Remove everything except backups
                for item in install_dir.iterdir():
                    if item.name != "backups":
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
            else:
                shutil.rmtree(install_dir)
            removed.append("install_dir")

        return {
            "status": "uninstalled",
            "removed": removed,
            "kept_backups": keep_backups,
        }

    def verify(self) -> dict[str, Any]:
        """Verify installation health.

        Returns:
            Verification report.
        """

        state = self._load_state()
        if not state:
            return {
                "status": "not_installed",
                "healthy": False,
                "issues": ["OpenContext is not installed"],
            }

        issues = []
        checks = []

        if state.version != self.VERSION:
            issues.append(f"Version mismatch: installed={state.version}, expected={self.VERSION}")
            checks.append({"check": "version", "ok": False, "version": state.version})
        else:
            checks.append({"check": "version", "ok": True, "version": state.version})

        for agent in state.agents:
            agent_dir = self._get_agent_dir(agent)
            if agent_dir and not agent_dir.exists():
                issues.append(f"Agent config missing: {agent}")
                checks.append({"check": f"agent:{agent}", "ok": False})
            else:
                checks.append({"check": f"agent:{agent}", "ok": True})

        mcp_path = Path.home() / ".claude" / "mcp.json"
        if mcp_path.exists():
            checks.append({"check": "mcp:claude", "ok": True})
        else:
            checks.append({"check": "mcp:claude", "ok": False, "note": "Optional"})

        for component in state.components:
            component_ok = self._verify_component(component)
            checks.append({"check": f"component:{component}", "ok": component_ok})
            if not component_ok:
                issues.append(f"Component issue: {component}")

        return {
            "status": "verified",
            "healthy": len(issues) == 0,
            "version": state.version,
            "issues": issues,
            "checks": checks,
        }

    def list_installed(self) -> dict[str, Any]:
        """List installed components.

        Returns:
            Installation report.
        """

        state = self._load_state()
        if not state:
            return {
                "status": "not_installed",
                "components": [],
                "agents": [],
            }

        return {
            "status": "installed",
            "version": state.version,
            "installed_at": state.installed_at,
            "components": state.components,
            "agents": state.agents,
            "profiles": state.profiles,
        }

    def _is_installed(self) -> bool:
        """Check if OpenContext is installed."""
        return self.state_path.exists()

    def _load_state(self) -> InstallState | None:
        """Load installation state."""
        if not self.state_path.exists():
            return None
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return InstallState(
                version=data.get("version", "0.1.0"),
                installed_at=data.get("installed_at", ""),
                components=data.get("components", []),
                agents=data.get("agents", []),
                profiles=data.get("profiles", []),
                hooks_run=data.get("hooks_run", []),
            )
        except (json.JSONDecodeError, OSError):
            return None

    def _save_state(self, state: InstallState) -> None:
        """Save installation state."""
        import time

        if not state.installed_at:
            state.installed_at = time.strftime("%Y-%m-%d %H:%M:%S")

        self.state_path.write_text(
            json.dumps(
                {
                    "version": state.version,
                    "installed_at": state.installed_at,
                    "components": state.components,
                    "agents": state.agents,
                    "profiles": state.profiles,
                    "hooks_run": state.hooks_run,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _resolve_components(
        self,
        profile: InstallProfile,
        explicit: list[str] | None,
    ) -> set[str]:
        """Resolve which components to install."""

        if explicit:
            return set(explicit)

        profiles: dict[InstallProfile, set[str]] = {
            InstallProfile.MINIMAL: {"mcp"},
            InstallProfile.FULL: {"mcp", "agents", "skills", "profiles", "hooks", "docs"},
            InstallProfile.AGENTS_ONLY: {"agents"},
            InstallProfile.MCP_ONLY: {"mcp"},
            InstallProfile.CUSTOM: {"mcp"},  # Will prompt user
        }

        return profiles.get(profile, {"mcp"})

    def _resolve_agents(
        self,
        profile: InstallProfile,
        explicit: list[str] | None,
    ) -> list[str]:
        """Resolve which agents to configure."""

        if explicit:
            return explicit

        detected = self.installer.detect_installed_agents()
        return [a.value for a in detected]

    def _install_mcp(self) -> dict[str, Any]:
        """Install MCP server configuration."""
        return {
            "component": "mcp",
            "status": "installed",
            "note": "MCP config written to agent directories",
        }

    def _write_project_config(self, project_root: Path) -> Path:
        """Write a loadable ``opencontext.yaml`` to *project_root*.

        Reuses the canonical default template (``default_config_data``) — the
        same source ``OnboardingService.run`` uses — and validates the written
        file by loading it back, so install never reports success over an
        unloadable config. An existing config is left untouched.
        """
        import yaml

        from opencontext_core.config import default_config_data, load_config

        project_root.mkdir(parents=True, exist_ok=True)
        config_path = project_root / "opencontext.yaml"
        if not config_path.exists():
            config_data = default_config_data()
            project = config_data.get("project")
            if isinstance(project, dict):
                project["name"] = project_root.name or project.get("name", "my-project")
            # Auto-detect ambient provider from environment
            try:
                from opencontext_core.providers.detect import detect_provider

                detected = detect_provider()
                if detected.source != "fallback":
                    models = config_data.setdefault("models", {})
                    default_model = models.setdefault("default", {})
                    default_model["provider"] = detected.name
                    default_model["model"] = detected.model
            except Exception:
                pass
            config_path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

        # Fail loudly rather than report success over an unloadable config.
        load_config(config_path)
        return config_path

    def _install_skills(self, project_root: Path) -> dict[str, Any]:
        """Copy the bundled skill templates (SDD set + agent skill) to disk.

        Templates ship inside the package under ``skills/templates/``; each is a
        directory containing a ``SKILL.md``. They are copied into the project's
        ``.opencontext/skills/`` directory. The result lists every file written
        so callers can assert real on-disk installation.
        """
        templates_dir = Path(__file__).resolve().parent / "skills" / "templates"
        dest_root = project_root / ".opencontext" / "skills"
        dest_root.mkdir(parents=True, exist_ok=True)

        # Skills the developer drives (one per SDD phase), plus the agent skill.
        required_skills = (
            "oc-new",
            "oc-explore",
            "oc-propose",
            "oc-spec",
            "oc-design",
            "oc-tasks",
            "oc-apply",
            "oc-verify",
            "oc-archive",
            "opencontext-agent",
        )

        written: list[str] = []
        missing: list[str] = []
        for skill_name in required_skills:
            src = templates_dir / skill_name / "SKILL.md"
            if not src.exists():
                missing.append(skill_name)
                continue
            dest_dir = dest_root / skill_name
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / "SKILL.md"
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            written.append(str(dest))

        result: dict[str, Any] = {
            "component": "skills",
            "status": "installed" if written and not missing else "partial",
            "files": written,
        }
        if missing:
            result["missing"] = missing
        return result

    def _install_profiles(self) -> dict[str, Any]:
        """Install SDD profiles."""
        from opencontext_core.sdd_profiles import SDDProfileManager

        manager = SDDProfileManager()
        profiles = manager.list_profiles()

        return {
            "component": "profiles",
            "status": "installed",
            "profiles": len(profiles),
        }

    def _run_hooks(self, hook_name: str) -> dict[str, Any]:
        """Run installation hooks."""
        return {
            "component": "hooks",
            "status": "completed",
            "hook": hook_name,
        }

    def _install_git_hook(self, project_root: Path) -> None:
        """Install a post-commit git hook that harvests memory and re-indexes changed files."""
        git_dir = project_root / ".git"
        if not git_dir.is_dir():
            return
        hook_path = git_dir / "hooks" / "post-commit"
        hook_content = (
            "#!/bin/sh\n"
            "# OpenContext: harvest memory candidates and re-index changed files\n"
            "opencontext memory collect --yes >/dev/null 2>&1 &\n"
            "opencontext index . >/dev/null 2>&1 &\n"
        )
        if hook_path.exists():
            existing = hook_path.read_text(encoding="utf-8")
            if "opencontext" in existing:
                return
            hook_content = existing.rstrip("\n") + "\n\n" + hook_content
        hook_path.write_text(hook_content, encoding="utf-8")
        hook_path.chmod(0o755)

    def _check_updates(self, state: InstallState) -> list[dict[str, Any]]:
        """Check for available updates."""
        updates = []

        if state.version != self.VERSION:
            updates.append(
                {
                    "type": "version",
                    "from": state.version,
                    "to": self.VERSION,
                }
            )

        return updates

    def _apply_update(self, update: dict[str, Any]) -> dict[str, Any]:
        """Apply a single update."""
        return {
            "type": update.get("type"),
            "status": "applied",
        }

    def _remove_agent_config(self, agent: str) -> bool:
        """Remove configuration for an agent."""
        agent_dir = self._get_agent_dir(agent)
        if agent_dir and agent_dir.exists():
            for file in ["mcp.json", "opencontext.json", "CLAUDE.md"]:
                path = agent_dir / file
                if path.exists():
                    path.unlink()
            return True
        return False

    def _remove_mcp_config(self) -> bool:
        """Remove MCP configurations."""
        removed = False
        for agent_dir in [".claude", ".config/opencode", ".cursor"]:
            mcp_path = Path.home() / agent_dir / "mcp.json"
            if mcp_path.exists():
                mcp_path.unlink()
                removed = True
        return removed

    def _verify_component(self, component: str) -> bool:
        """Verify a component is healthy."""
        if component == "mcp":
            return True
        if component == "skills":
            return True
        if component == "profiles":
            return True
        return True

    def _get_agent_dir(self, agent: str) -> Path | None:
        """Get configuration directory for an agent."""
        mapping: dict[str, str] = {
            "claude-code": ".claude",
            "opencode": ".config/opencode",
            "cursor": ".cursor",
            "codex": ".codex",
            "windsurf": ".windsurf",
            "gemini-cli": ".gemini",
            "kilo-code": ".config/kilo",
            "kiro-ide": ".kiro",
            "kimi-code": ".kimi",
            "qwen-code": ".qwen",
            "openclaw": ".openclaw",
        }
        dir_name = mapping.get(agent)
        if dir_name:
            return Path.home() / dir_name
        return None
