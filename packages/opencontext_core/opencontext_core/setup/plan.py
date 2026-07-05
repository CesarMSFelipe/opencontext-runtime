"""Install plan — models and resolver for setup actions.

An InstallPlan describes what will happen during a setup operation,
supports --dry-run preview, and tracks component state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from opencontext_core.setup.presets import (
    COMPONENT_CATALOG,
    ComponentStatus,
    resolve_preset_components,
)


@dataclass
class InstallAction:
    """A single action in the install plan."""

    type: str  # "install", "configure", "enable", "skip"
    component_id: str
    component_name: str
    description: str
    status: str = "pending"  # pending, done, skipped, failed
    details: str = ""


@dataclass
class FileChange:
    """A file that will be created or modified."""

    path: str
    action: str  # "create", "modify", "delete"
    description: str


@dataclass
class InstallPlan:
    """Complete plan for a setup operation."""

    preset: str
    profile: str
    components: list[str]
    actions: list[InstallAction] = field(default_factory=list)
    file_changes: list[FileChange] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def total_actions(self) -> int:
        return len(self.actions)

    @property
    def completed_actions(self) -> int:
        return sum(1 for a in self.actions if a.status == "done")

    @property
    def is_complete(self) -> bool:
        return all(a.status == "done" for a in self.actions)

    def summary_lines(self) -> list[str]:
        """Generate human-readable summary lines."""
        lines = [
            f"Preset: {self.preset}",
            f"Profile: {self.profile}",
            f"Components ({len(self.components)}): {', '.join(self.components)}",
            "",
            "Actions:",
        ]
        for action in self.actions:
            icon = {
                "pending": "  ·",
                "done": "  ✓",
                "skipped": "  -",
                "failed": "  ✗",
            }.get(action.status, "  ·")
            lines.append(f"  {icon} {action.description}")
        if self.file_changes:
            lines.append("")
            lines.append("Files:")
            for fc in self.file_changes:
                icon = "  +" if fc.action == "create" else "  ~"
                lines.append(f"  {icon} {fc.path}  ({fc.description})")
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        return lines

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON output."""
        return {
            "preset": self.preset,
            "profile": self.profile,
            "components": self.components,
            "actions": [a.__dict__ for a in self.actions],
            "file_changes": [f.__dict__ for f in self.file_changes],
            "dependencies": self.dependencies,
            "warnings": self.warnings,
            "created_at": self.created_at,
        }


def build_plan(
    preset_id: str | None = None,
    profile_id: str | None = None,
    components: list[str] | None = None,
) -> InstallPlan:
    """Build an install plan from preset and/or component selections.

    Args:
        preset_id: Named preset to use (mutually exclusive with components).
        profile_id: Profile to apply.
        components: Explicit component list.

    Returns:
        InstallPlan with all actions and file changes resolved.
    """

    resolved_components: list[str] = []

    if preset_id:
        resolved_components = resolve_preset_components(preset_id)
    elif components:
        resolved_components = list(dict.fromkeys(components))  # dedup, preserve order
    else:
        # Default: context-first preset
        resolved_components = resolve_preset_components("context-first")

    if profile_id is None:
        if preset_id:
            from opencontext_core.setup.presets import PRESET_CATALOG

            preset = PRESET_CATALOG.get(preset_id)
            if preset:
                profile_id = preset.profile
        if profile_id is None:
            profile_id = "developer"

    plan = InstallPlan(
        preset=preset_id or "custom",
        profile=profile_id,
        components=resolved_components,
    )

    user_config_path = Path.home() / ".config" / "opencontext" / "user-config.json"

    # Build actions for each component
    for cid in resolved_components:
        comp = COMPONENT_CATALOG.get(cid)
        if not comp:
            plan.actions.append(
                InstallAction("skip", cid, cid, f"Unknown component: {cid}", status="skipped")
            )
            continue

        # Check if already installed
        status = _check_component_status(cid)

        if status == ComponentStatus.INSTALLED:
            plan.actions.append(
                InstallAction(
                    "skip", cid, comp.name, f"{comp.name} already installed", status="skipped"
                )
            )
            continue

        # Check for blockers
        if status == ComponentStatus.BLOCKED:
            plan.warnings.append(f"{comp.name} blocked — missing dependencies")
            plan.actions.append(
                InstallAction("skip", cid, comp.name, f"{comp.name} blocked", status="skipped")
            )
            continue

        # Check network requirement
        if comp.requires_network:
            plan.warnings.append(f"{comp.name} requires network access")

        # Add dependency info
        if comp.requires_python_package:
            plan.dependencies.append(comp.requires_python_package)

        plan.actions.append(
            InstallAction(
                "install",
                cid,
                comp.name,
                f"Install {comp.name}: {comp.description}",
            )
        )

    # File changes
    plan.file_changes.append(FileChange(str(user_config_path), "modify", "Update user preferences"))

    mcp_path = Path.home() / ".config" / "opencode" / "opencode.json"
    if "mcp-server" in resolved_components:
        plan.file_changes.append(FileChange(str(mcp_path), "modify", "Configure MCP for OpenCode"))

    plugins_dir = Path.home() / ".config" / "opencontext" / "plugins"
    for cid in resolved_components:
        if cid == "plugins":
            plan.file_changes.append(FileChange(str(plugins_dir), "create", "Plugin directory"))
            break

    return plan


def _check_component_status(component_id: str) -> ComponentStatus:
    """Check if a component is already installed based on user config.

    On first run (no saved config yet), all components show as NOT_INSTALLED
    so the setup plan shows meaningful pending actions.
    """

    from opencontext_core.user_prefs import UserConfigStore

    store = UserConfigStore()
    prefs = store.load()

    # First run — no explicit config yet, show all as pending
    if prefs.first_run:
        return ComponentStatus.NOT_INSTALLED

    # Map component IDs to user prefs features
    feature_map = {
        "knowledge-graph": prefs.features.knowledge_graph,
        "call-graph": prefs.features.call_graph,
        "learning": prefs.features.learning_system,
        "governance": prefs.features.governance,
        "mcp-server": prefs.features.mcp_server,
        "git-integration": prefs.features.git_integration,
        "embeddings": prefs.features.embeddings,
        "semantic-search": prefs.features.semantic_search,
    }

    if component_id in feature_map:
        return (
            ComponentStatus.INSTALLED
            if feature_map[component_id]
            else ComponentStatus.NOT_INSTALLED
        )

    # Plugins check
    if component_id == "plugins":
        return (
            ComponentStatus.INSTALLED
            if len(prefs.installed_plugins) > 0
            else ComponentStatus.NOT_INSTALLED
        )

    return ComponentStatus.NOT_INSTALLED
