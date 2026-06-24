"""AgenticInstallPlan — dry-run planning for opencontext install agentic flags.

NOTE: This module must NOT import from opencontext_cli (main.py or setup_cmd.py)
to avoid circular imports. It depends only on opencontext_core.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from opencontext_core.agentic.config import (
    AgenticFlowConfig,
    BudgetMode,
    ComponentId,
    FlowMode,
    GitMode,
    MemoryMode,
    OpenSpecMode,
    PresetId,
)


@dataclass
class AgenticInstallPlan:
    """Resolved install plan — what the agentic flags would do."""

    preset: PresetId
    components: list[ComponentId]
    memory_mode: MemoryMode
    flow_mode: FlowMode
    openspec_mode: OpenSpecMode
    budget_mode: BudgetMode
    git_mode: GitMode
    engram_action: str | None  # e.g. "install via brew" or "already detected" or None
    files_to_write: list[str] = field(default_factory=list)
    provisioning_commands: list[list[str]] = field(default_factory=list)


def build_install_plan(
    config: AgenticFlowConfig,
    *,
    agents: list[str] | None = None,
) -> AgenticInstallPlan:
    """Convert an AgenticFlowConfig into a human-readable install plan.

    When *agents* is provided, emits per-agent Engram provisioning commands.
    """
    engram_action = _resolve_engram_action(config)
    files = _resolve_files_to_write(config)
    provisioning_commands = _resolve_provisioning_commands(config, agents)
    return AgenticInstallPlan(
        preset=config.preset,
        components=list(config.components),
        memory_mode=config.memory_mode,
        flow_mode=config.flow_mode,
        openspec_mode=config.openspec_mode,
        budget_mode=config.budget_mode,
        git_mode=config.git_mode,
        engram_action=engram_action,
        files_to_write=files,
        provisioning_commands=provisioning_commands,
    )


def render_dry_run(plan: AgenticInstallPlan) -> str:
    """Render the install plan as a human-readable string for --dry-run output."""
    lines: list[str] = [
        "OpenContext Agentic Install Plan (dry-run — no changes made)",
        "=" * 58,
        f"  Preset       : {plan.preset}",
        f"  Components   : {', '.join(plan.components) if plan.components else '(none)'}",
        f"  Memory mode  : {plan.memory_mode}",
        f"  Flow mode    : {plan.flow_mode}",
        f"  OpenSpec     : {plan.openspec_mode}",
        f"  Budget mode  : {plan.budget_mode}",
        f"  Git mode     : {plan.git_mode}",
    ]
    if plan.engram_action:
        lines.append(f"  Engram       : {plan.engram_action}")
    if plan.files_to_write:
        lines.append("  Files to write:")
        for f in plan.files_to_write:
            lines.append(f"    - {f}")
    if plan.provisioning_commands:
        lines.append("  Provisioning commands:")
        for cmd in plan.provisioning_commands:
            lines.append(f"    $ {' '.join(cmd)}")
    lines.append("")
    lines.append("Run without --dry-run to apply.")
    return "\n".join(lines)


def _resolve_engram_action(config: AgenticFlowConfig) -> str | None:
    if not config.install_engram_if_missing:
        return None
    from opencontext_core.memory.engram_bridge import detect_engram

    if detect_engram():
        return "already detected"
    from opencontext_core.memory.engram_provisioning import EngramProvisioner

    plan = EngramProvisioner().plan_install()
    if plan.install_command:
        return f"install via {plan.install_command[0]}"
    return "manual install required (see https://github.com/dstotijn/engram)"


def _resolve_provisioning_commands(
    config: AgenticFlowConfig,
    agents: list[str] | None,
) -> list[list[str]]:
    """Return Engram install + setup commands based on config and agent list."""
    from opencontext_core.agentic.config import MemoryMode
    from opencontext_core.memory.engram_provisioning import EngramProvisioner

    wants_engram = (
        ComponentId.ENGRAM in config.components
        or config.memory_mode in {MemoryMode.AUTO, MemoryMode.ENGRAM, MemoryMode.HYBRID, MemoryMode.ENGRAM_ONLY}
    )
    if not wants_engram:
        return []

    provisioner = EngramProvisioner()
    commands: list[list[str]] = []
    seen: set[str] = set()

    effective_agents: list[str | None] = list(agents) if agents else [None]
    for agent in effective_agents:
        plan = provisioner.plan_install(agent=agent)
        if not plan.detected and config.install_engram_if_missing:
            if plan.install_command:
                cmd_key = " ".join(plan.install_command)
                if cmd_key not in seen:
                    commands.append(plan.install_command)
                    seen.add(cmd_key)
        if plan.setup_command:
            cmd_key = " ".join(plan.setup_command)
            if cmd_key not in seen:
                commands.append(plan.setup_command)
                seen.add(cmd_key)

    return commands


def _resolve_files_to_write(config: AgenticFlowConfig) -> list[str]:
    files: list[str] = ["opencontext.yaml"]
    if config.openspec_mode != OpenSpecMode.OFF:
        files.append("openspec/config.yaml")
    if config.budget_mode != BudgetMode.OFF:
        files.append(".opencontext/budget_policy.json")
    return files


if __name__ == "__main__":
    from opencontext_core.agentic.presets import preset_config

    cfg = preset_config(PresetId.AGENTIC_MINIMAL)
    plan = build_install_plan(cfg)
    assert plan.preset == PresetId.AGENTIC_MINIMAL
    text = render_dry_run(plan)
    assert "dry-run" in text
    assert "agentic-minimal" in text

    print("agentic/install_plan.py self-check passed.")
