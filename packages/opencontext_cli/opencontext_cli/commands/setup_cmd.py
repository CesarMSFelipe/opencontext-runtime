"""Setup CLI command — interactive setup with presets, profiles, and dry-run."""

from __future__ import annotations

import json
from typing import Any

from rich.table import Table
from rich.text import Text

from opencontext_core import prompts
from opencontext_core.adapters.agent_manifest import AgentTarget
from opencontext_core.agent_installer import AgentInstaller
from opencontext_core.agent_installer import AgentTarget as GlobalAgentTarget
from opencontext_core.configurator import KNOWN_AGENTS, Configurator
from opencontext_core.dx.console_styles import console
from opencontext_core.dx.wizard_frame import WizardStep, render_frame
from opencontext_core.runtime import OpenContextRuntime
from opencontext_core.sdd_runtime import write_sdd_context
from opencontext_core.setup.plan import InstallAction, build_plan
from opencontext_core.setup.presets import (
    get_available_components,
    get_available_presets,
    get_available_profiles,
    resolve_preset_components,
)
from opencontext_core.user_prefs import UserConfigStore


def _save_install_ledger(report: dict[str, Any]) -> None:
    """Persist written file paths to InstallState so uninstall --full can clean up."""
    try:
        from opencontext_core.install_manager import InstallationManager, InstallState

        all_files = [f for r in report.get("results", []) for f in r.get("files", [])]
        all_files.extend(report.get("extra_files_written", []))
        if not all_files:
            return
        mgr = InstallationManager()
        existing = mgr._load_state()
        existing_files = existing.files if existing else []
        merged = list(dict.fromkeys([*existing_files, *all_files]))
        state = existing if existing else InstallState()
        state.files = merged
        mgr._save_state(state)
    except Exception:
        pass


# Detail cards for the interactive setup steps — the shared wizard frame renders
# these in the config-TUI info-pane format (Current/Effect/Recommended/Risk/CLI).
_SETUP_WIZARD_STEPS: dict[str, WizardStep] = {
    "preset": WizardStep(
        title="Preset",
        effect="Chooses which component set the install plan applies.",
        recommended="context-first for most projects.",
        risk="Nothing is written until you confirm the plan in the last step.",
        cli="opencontext setup --preset <id>",
    ),
    "profile": WizardStep(
        title="Profile",
        effect="Applies security mode and feature defaults for a role.",
        recommended="The profile suggested for your preset.",
        risk="security-officer profiles lock down external providers.",
        cli="opencontext setup --profile <id>",
    ),
    "components": WizardStep(
        title="Components",
        effect="Selects the exact components the plan installs.",
        recommended="Keep the preset's component list.",
        risk="Removing knowledge-graph disables context packs and KG queries.",
        cli="opencontext setup --component <id> (repeatable)",
    ),
    "agents_tdd": WizardStep(
        title="Agent clients & TDD",
        effect="Writes MCP config + instructions per agent and sets TDD enforcement.",
        recommended="The agents you actually use; TDD ask.",
        risk="strict TDD requires a working test harness in the project.",
        cli="opencontext setup --agent <id> --tdd <ask|strict|off>",
    ),
    "sdd_profile": WizardStep(
        title="SDD model profile",
        effect="Routes SDD phases (explore/design/apply...) to a model profile.",
        recommended="default — one model for all phases.",
        risk="premium may cost more; cheap may reduce design quality.",
        cli="opencontext setup --sdd-profile <profile>",
    ),
    "review": WizardStep(
        title="Plan review",
        effect="Shows every planned action; confirming applies the plan.",
        recommended="Read the action list before applying.",
        risk="Apply writes config, agent files, SDD context, and indexes the project.",
        cli="opencontext setup --dry-run",
    ),
}


def _wizard_clear(
    step: int,
    total: int,
    key: str,
    context: list[tuple[str, str]] | None = None,
) -> None:
    """Clear the terminal and render the shared wizard frame for one step.

    Choices made so far (*context*) show as the card's ``Current:`` line so the
    breadcrumb trail survives the per-step clear. Renders nothing on a non-TTY.
    """
    card = _SETUP_WIZARD_STEPS[key]
    if context:
        card = card.with_current(" · ".join(f"{k} {v}" for k, v in context))
    render_frame(step, total, card)


def _check_first_run() -> bool:
    """Check if this is a first run and suggest onboard if so."""
    store = UserConfigStore()
    prefs = store.load()
    if prefs.first_run:
        console.print()
        console.panel(
            "[bold yellow]First Run Detected[/bold yellow]\n"
            "It looks like you haven't run [bold]opencontext install[/bold] yet.\n"
            "For a complete project setup in one step, run:\n\n"
            "  [bold cyan]opencontext install[/bold cyan]\n\n"
            "This will auto-detect your project, create your config, index your code,\n"
            "and configure SDD/TDD, agent integrations, and the harness workflow.",
            style="warning",
            fit=True,
        )
        return True
    return False


def add_setup_parser(subparsers: Any) -> None:
    """Add setup command parser.

    ``setup`` is the headline "configure my agent(s)" action. Given agent ids
    (or ``--all``, or nothing — in which case installed agents are detected) it
    writes each agent's MCP entry and managed instructions block via
    ``Configurator``. The preset/profile/component flags below drive the older
    plan-based project installer and remain available for back-compat.
    """
    setup_parser = subparsers.add_parser(
        "setup",
        help="Configure your AI agent(s) — MCP + instructions. Use --all or name agents.",
        description=(
            "Configure existing AI coding agents to use OpenContext.\n\n"
            "  opencontext setup                 Configure every detected agent\n"
            "  opencontext setup claude-code      Configure one agent\n"
            "  opencontext setup --all            Configure every known agent\n"
            "  opencontext setup --scope local    Write project-local config (default)\n"
            "  opencontext setup --dry-run        Show what would be written\n\n"
            f"Known agents: {', '.join(KNOWN_AGENTS)}"
        ),
    )
    setup_parser.add_argument(
        "agents",
        nargs="*",
        metavar="AGENT",
        help="Agent id(s) to configure (e.g. claude-code opencode codex).",
    )
    setup_parser.add_argument(
        "--all",
        dest="all_agents",
        action="store_true",
        help="Configure every known agent.",
    )
    setup_parser.add_argument(
        "--scope",
        choices=["global", "local"],
        default="local",
        help="Where instructions are written: local (project) or global (home).",
    )
    setup_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompts.",
    )
    setup_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the configuration report as JSON.",
    )
    setup_parser.add_argument(
        "--preset",
        choices=["full", "context-essential", "enterprise", "air-gapped", "context-first"],
        help="Preset to install (legacy plan-based installer).",
    )
    setup_parser.add_argument(
        "--profile",
        choices=["developer", "security-officer", "researcher", "minimal"],
        help="Profile to apply.",
    )
    setup_parser.add_argument(
        "--component",
        action="append",
        dest="components",
        help="Component to install (can be repeated).",
    )
    setup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the plan without applying changes.",
    )
    setup_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use defaults without prompts.",
    )
    setup_parser.add_argument(
        "--agent",
        action="append",
        default=None,
        help="Agent to configure. Repeat or comma-separate. Default: opencode.",
    )
    setup_parser.add_argument(
        "--tdd",
        choices=["ask", "strict", "off"],
        default="ask",
        help="TDD behavior for SDD agents: ask each change, strict, or off.",
    )
    setup_parser.add_argument("--root", default=".", help="Project root to initialize.")
    setup_parser.add_argument(
        "--max-tokens",
        type=int,
        default=3000,
        help="Default per-phase SDD context budget.",
    )
    setup_parser.add_argument(
        "--sdd-profile",
        choices=["default", "cheap", "hybrid", "premium"],
        default=None,
        help="SDD model profile: which models to use per phase.",
    )
    setup_parser.add_argument(
        "--orchestrator-profile",
        choices=["opencontext", "solo-compact", "multi-phase", "subagent-native"],
        default=None,
        help="Orchestration strategy for SDD agents.",
    )
    setup_parser.add_argument(
        "--execution-mode",
        choices=["auto", "manual"],
        default="auto",
        help="Guided SDD execution mode.",
    )
    setup_parser.add_argument(
        "--artifact-mode",
        choices=["engram", "openspec", "hybrid", "none"],
        default="hybrid",
        help="SDD artifact persistence mode.",
    )


def handle_setup(args: Any) -> None:
    """Handle setup command.

    Routes to one of two flows. When the invocation looks like an
    agent-configuration request (positional agents, ``--all``, or no
    preset/profile/component selectors) it runs the ``Configurator`` flow.
    Otherwise it falls back to the legacy plan-based installer.
    """
    preset = getattr(args, "preset", None)
    profile = getattr(args, "profile", None)
    components = getattr(args, "components", None)

    if _is_configurator_request(args):
        _run_configurator(args)
        return

    dry_run = getattr(args, "dry_run", False)
    non_interactive = getattr(args, "non_interactive", False)
    agents = _parse_agents(getattr(args, "agent", None))
    tdd_mode = getattr(args, "tdd", "ask")
    root = getattr(args, "root", ".")
    max_tokens = getattr(args, "max_tokens", 3000)
    sdd_profile = getattr(args, "sdd_profile", None)
    orchestrator_profile = getattr(args, "orchestrator_profile", None)
    execution_mode = getattr(args, "execution_mode", "auto")
    artifact_mode = getattr(args, "artifact_mode", "hybrid")

    if non_interactive:
        _run_automated(
            preset,
            profile,
            components,
            dry_run,
            agents,
            tdd_mode,
            root,
            max_tokens,
            sdd_profile,
            orchestrator_profile,
            execution_mode,
            artifact_mode,
        )
    else:
        _run_interactive(
            preset,
            profile,
            components,
            dry_run,
            agents,
            tdd_mode,
            root,
            max_tokens,
            sdd_profile,
            orchestrator_profile,
            execution_mode,
            artifact_mode,
        )


def _is_configurator_request(args: Any) -> bool:
    """Decide whether to use the agent ``Configurator`` flow.

    The legacy plan-based installer owns any invocation that selects a preset,
    profile, or explicit component. Everything else — naming agents, ``--all``,
    or a bare ``opencontext setup`` — is an agent-configuration request.
    """
    if getattr(args, "preset", None) or getattr(args, "profile", None):
        return False
    if getattr(args, "components", None):
        return False
    return True


def _run_configurator(args: Any) -> None:
    """Configure agents via ``Configurator`` and print a clean report."""
    # Deferred import avoids a circular import at module load (main imports us).
    from opencontext_cli.main import _resolve_flag

    root = getattr(args, "root", ".")
    scope = getattr(args, "scope", "local")
    dry_run = _resolve_flag(getattr(args, "dry_run", False), "OPENCONTEXT_DRY_RUN")
    json_output = _resolve_flag(getattr(args, "json", False), "OPENCONTEXT_JSON")
    requested = _parse_setup_agents(getattr(args, "agents", None))
    want_all = getattr(args, "all_agents", False)

    if not json_output:
        console.header("Configure Agents")

    configurator = Configurator(project_root=root)

    if want_all:
        agents = list(KNOWN_AGENTS)
        source = "all"
    elif requested:
        agents = requested
        source = "named"
    else:
        agents = configurator.detect_installed()
        source = "detected"

    known = set(KNOWN_AGENTS)
    unknown = [a for a in agents if a not in known]
    valid = [a for a in agents if a in known]

    if not valid:
        _report_no_agents(source, unknown, json_output)
        return

    if dry_run:
        report = configurator.configure(valid, scope=scope, dry_run=True)
        if unknown:
            report["skipped"] = unknown
        _report_dry_run(report, unknown, json_output)
        return

    yes = _resolve_flag(getattr(args, "yes", False), "OPENCONTEXT_YES")
    if not _confirm_configure(valid, scope, yes=yes, json_output=json_output):
        console.warning("Setup cancelled.")
        return

    report = configurator.configure(valid, scope=scope)
    if unknown:
        report["skipped"] = unknown
    _record_extra_files(report, _maybe_write_stack_standards(root, scope, report))
    _record_extra_files(report, _maybe_write_gitignore(root, scope))
    _save_install_ledger(report)
    _report_configured(report, unknown, json_output)


def _record_extra_files(report: dict[str, Any], files: list[str]) -> None:
    if files:
        report.setdefault("extra_files_written", []).extend(files)


def _maybe_write_gitignore(root: Any, scope: str) -> list[str]:
    """Keep the local index/memory out of git so teammates don't clone a stale
    binary graph — while the shareable config (opencontext.yaml, AGENTS.md) stays
    committed. Managed block, project scope only, best-effort.

    Only writes the .gitignore block when mode=local (in-repo storage) or legacy
    in-repo state dirs are detected. In user mode (default XDG), the block is
    skipped because no in-repo state is written.
    """
    if scope != "local":
        return []
    try:
        from pathlib import Path

        from opencontext_core.config import load_config_or_defaults
        from opencontext_core.configurator.filemerge import (
            inject_managed_lines,
            write_text_atomic,
        )
        from opencontext_core.paths import StorageMode, detect_legacy

        root_path = Path(root)
        _cfg_path = root_path / "opencontext.yaml"
        if _cfg_path.exists():
            _cfg = load_config_or_defaults(_cfg_path)
            # Only skip the .gitignore block when we know mode=user and there are
            # no legacy dirs (in-repo state is not written in user mode).
            if _cfg.storage.mode != StorageMode.local and detect_legacy(root_path) is None:
                return []
        # No config found yet (first-time setup) — write the block as a safe default.

        path = root_path / ".gitignore"
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        merged = inject_managed_lines(existing, "storage", [".storage/", ".opencontext/"])
        if write_text_atomic(path, merged):
            console.success("Updated .gitignore (keeps the local index out of git).")
            return [str(path)]
    except Exception:
        return []
    return []


def _maybe_write_stack_standards(root: Any, scope: str, report: dict[str, Any]) -> list[str]:
    """Prepare configured agents for the detected stack by writing AGENTS.md.

    Best-effort and project-scoped: stack standards are project-specific, so only
    write them for a local (in-project) configuration. Never fail setup over it.
    """
    if scope != "local":
        return []
    try:
        from pathlib import Path

        from opencontext_cli.commands.stack_cmd import write_stack_standards

        path = Path(root) / "AGENTS.md"
        changed, chosen = write_stack_standards(Path(root))
    except Exception:
        return []
    if changed and chosen:
        report["stack_standards"] = chosen
        console.success(f"Prepared AGENTS.md with standards for: {', '.join(chosen)}")
        return [str(path)]
    return []


def _confirm_configure(agents: list[str], scope: str, *, yes: bool, json_output: bool) -> bool:
    """Confirm before writing, unless --yes/--json or a non-interactive stdin."""
    import sys

    if yes or json_output or not sys.stdin.isatty():
        return True
    console.print(f"About to configure: [bold]{', '.join(agents)}[/] (scope: {scope})")
    return prompts.confirm("Proceed?", default=True)


def _parse_setup_agents(values: list[str] | None) -> list[str]:
    """Normalize positional/comma-separated agent ids, de-duplicating order."""
    if not values:
        return []
    agents: list[str] = []
    for raw in values:
        for item in raw.split(","):
            normalized = item.strip()
            if normalized and normalized not in agents:
                agents.append(normalized)
    return agents


def _report_no_agents(source: str, unknown: list[str], json_output: bool) -> None:
    if json_output:
        print(json.dumps({"status": "no_agents", "agents_configured": 0, "skipped": unknown}))
        return
    if unknown:
        console.warning(f"Unknown agent(s), skipped: {', '.join(unknown)}")
    elif source == "detected":
        console.info("No installed agents detected.")
    else:
        console.info("No agents to configure.")
    console.dim(f"  Name an agent or use --all. Known agents: {', '.join(KNOWN_AGENTS)}")


def _report_dry_run(report: dict[str, Any], unknown: list[str], json_output: bool) -> None:
    if json_output:
        print(json.dumps(report, indent=2))
        return
    console.warning("Dry run — no changes made.")
    console.print(f"  Scope: [cyan]{report.get('scope')}[/]")
    console.print("  Would configure:")
    for result in report.get("results", []):
        console.print(f"    • {result['agent']}")
        for entry in result.get("plan", []):
            console.print(f"      [dim]{entry['action']}: {entry['path']}[/]")
    for agent in unknown:
        console.print(f"    [dim]- {agent} (unknown, skipped)[/]")


def _report_configured(report: dict[str, Any], unknown: list[str], json_output: bool) -> None:
    if json_output:
        print(json.dumps(report, indent=2))
        return
    count = report.get("agents_configured", 0)
    console.panel(
        f"[bold green]Configured {count} agent(s)[/bold green]   "
        f"scope: [cyan]{report.get('scope')}[/]",
        style="success",
        fit=True,
    )
    for result in report.get("results", []):
        console.print(f"  [bold]{result['agent']}[/]")
        for file_path in result.get("files", []):
            console.print(f"    [dim]{file_path}[/]")
    for agent in unknown:
        console.warning(f"- {agent} (unknown, skipped)")


def _run_interactive(
    preset: str | None,
    profile: str | None,
    components: list[str] | None,
    dry_run: bool,
    agents: list[str],
    tdd_mode: str,
    root: str,
    max_tokens: int,
    sdd_profile: str | None = None,
    orchestrator_profile: str | None = None,
    execution_mode: str = "auto",
    artifact_mode: str = "hybrid",
) -> None:
    """Run interactive setup with rich prompts."""
    # ── Step 1: Preset ──────────────────────────────────────────────────
    if not preset:
        _wizard_clear(1, 6, "preset")
        preset = _choose_preset()

    # ── Step 2: Profile ─────────────────────────────────────────────────
    if not profile:
        _wizard_clear(2, 6, "profile", [("preset", preset)])
        profile = _choose_profile(preset)

    # ── Step 3: Components ──────────────────────────────────────────────
    if not components:
        _wizard_clear(3, 6, "components", [("preset", preset), ("profile", profile)])
        components = resolve_preset_components(preset)
        console.print(f"[bold]Components ({len(components)}):[/]")
        for c in components:
            console.print(f"  • {c}")
        if not prompts.confirm("Continue with these components?", default=True):
            custom_components = _choose_components()
            if custom_components:
                components = custom_components

    # ── Step 4: Agent clients + TDD mode ────────────────────────────────
    _wizard_clear(
        4,
        6,
        "agents_tdd",
        [("preset", preset), ("profile", profile), ("components", str(len(components)))],
    )
    agents = _choose_agents(agents)
    tdd_mode = _choose_tdd_mode(tdd_mode)

    # ── Step 5: SDD model profile ────────────────────────────────────────
    if not sdd_profile:
        _wizard_clear(
            5,
            6,
            "sdd_profile",
            [("preset", preset), ("profile", profile), ("tdd", tdd_mode)],
        )
        sdd_profile = _choose_sdd_profile()

    # ── Step 6: Plan review + confirm ────────────────────────────────────
    _wizard_clear(
        6,
        6,
        "review",
        [("preset", preset), ("profile", profile), ("tdd", tdd_mode), ("sdd", sdd_profile)],
    )
    plan = build_plan(preset_id=preset, profile_id=profile, components=components)
    _show_plan(plan)
    console.print(f"\n[bold]Agents:[/] {', '.join(agents)}")
    console.print(f"[bold]TDD mode:[/] {tdd_mode}")
    console.print(f"[bold]SDD model profile:[/] {sdd_profile}")
    console.print(f"[bold]SDD token budget/phase:[/] {max_tokens}")
    if orchestrator_profile:
        console.print(f"[bold]Orchestrator profile:[/] {orchestrator_profile}")

    if dry_run:
        console.warning("Dry run — no changes made.")
        return

    if not prompts.confirm("Apply this plan?", default=True):
        console.warning("Setup cancelled.")
        return

    # ── Execute (spinners) ───────────────────────────────────────────────
    try:
        console.clear()
    except Exception:
        pass
    _execute_plan(
        plan,
        agents,
        tdd_mode,
        root,
        max_tokens,
        sdd_profile,
        orchestrator_profile,
        execution_mode,
        artifact_mode,
    )
    console.print()
    console.panel(
        "[bold green]✓ Setup Complete[/bold green]\n"
        "OpenContext SDD/TDD, graph, memory, and selected agents are ready.",
        style="success",
        fit=True,
    )


def _run_automated(
    preset: str | None,
    profile: str | None,
    components: list[str] | None,
    dry_run: bool,
    agents: list[str],
    tdd_mode: str,
    root: str,
    max_tokens: int,
    sdd_profile: str | None = None,
    orchestrator_profile: str | None = None,
    execution_mode: str = "auto",
    artifact_mode: str = "hybrid",
) -> None:
    """Run automated setup (non-interactive)."""
    console.header("Setup")
    _check_first_run()

    if not preset and not components:
        preset = "context-first"

    plan = build_plan(
        preset_id=preset,
        profile_id=profile,
        components=components,
    )

    if dry_run:
        console.print("[bold]── Setup Plan (dry-run) ──[/]")
        for line in plan.summary_lines():
            console.print(line)
        return

    _execute_plan(
        plan,
        agents,
        tdd_mode,
        root,
        max_tokens,
        sdd_profile or "default",
        orchestrator_profile,
        execution_mode,
        artifact_mode,
    )
    console.success("Setup complete.")


def _choose_preset() -> str:
    """Interactive preset selection."""
    presets = get_available_presets()

    def preset_sort_key(p: Any) -> tuple[int, str]:
        if p.id == "context-first":
            return (0, p.id)
        return (1, p.id)

    sorted_presets = sorted(presets, key=preset_sort_key)

    console.print("\n[bold]Available Presets:[/]")
    # NOTE: deliberate exception — this table needs per-column styling that
    # console_styles.table (single brand column style) cannot represent.
    table = Table(box=None)
    table.add_column("Option", style="cyan")
    table.add_column("Preset", style="bold")
    table.add_column("Description")
    table.add_column("Components")

    for i, p in enumerate(sorted_presets, 1):
        components = resolve_preset_components(p.id)
        marker = " [default]" if p.id == "context-first" else ""
        name = p.name + marker
        table.add_row(
            str(i),
            name,
            p.description,
            ", ".join(components),
        )
    console.print(table)

    return str(
        prompts.select(
            "Select preset",
            [(p.id, f"{p.name} — {p.description}") for p in sorted_presets],
            default=sorted_presets[0].id,
        )
    )


def _choose_profile(preset: str | None = None) -> str:
    """Interactive profile selection."""
    profiles = get_available_profiles()

    suggestions = {
        "full": "developer",
        "context-essential": "minimal",
        "enterprise": "security-officer",
        "air-gapped": "security-officer",
        "context-first": "minimal",
    }
    default = suggestions.get(preset or "", "developer")
    default_idx = next((i for i, p in enumerate(profiles) if p.id == default), 0)

    return str(
        prompts.select(
            "Select profile",
            [
                (
                    p.id,
                    f"{p.name} — {p.description}" + (" (recommended)" if p.id == default else ""),
                )
                for p in profiles
            ],
            default=profiles[default_idx].id,
        )
    )


def _parse_agents(values: list[str] | None) -> list[str]:
    if not values:
        return ["opencode"]
    agents: list[str] = []
    for raw in values:
        for item in raw.split(","):
            normalized = item.strip()
            if normalized and normalized not in agents:
                agents.append(normalized)
    return agents or ["opencode"]


def _choose_agents(default_agents: list[str]) -> list[str]:
    supported = [target.value for target in AgentTarget]
    selected = list(dict.fromkeys(default_agents))
    chosen = prompts.checkbox(
        "Agent clients to configure",
        list(supported),
        defaults=selected,
        require_one=True,
    )
    return chosen or ["opencode"]


def _choose_tdd_mode(default: str) -> str:
    labels = {
        "ask": "ask — agent asks per change (recommended)",
        "strict": "strict — tests first whenever a harness exists",
        "off": "off — SDD still works but TDD is optional",
    }
    return str(
        prompts.select(
            "TDD behavior",
            [(mode, label) for mode, label in labels.items()],
            default=default if default in labels else "ask",
        )
    )


def _choose_sdd_profile() -> str:
    labels = {
        "default": "default — use one model for all phases",
        "cheap": "cheap — fast/free models for exploration, premium for design/verify",
        "hybrid": "hybrid — mix of cheap and premium models per phase",
        "premium": "premium — strongest models for all phases",
    }
    return str(
        prompts.select(
            "SDD model profile",
            [(p, label) for p, label in labels.items()],
            default="default",
        )
    )


def _choose_components() -> list[str]:
    """Interactive component selection (space to toggle, Enter to confirm)."""
    components = get_available_components()
    return prompts.checkbox(
        "Select components",
        [(comp.id, comp.name) for comp in components],
    )


def _show_plan(plan: Any) -> None:
    """Display the install plan."""
    from rich.table import Table as RichTable

    console.print("\n[bold]── Install Plan ──[/]")
    console.print(f"  Preset: [cyan]{plan.preset}[/]")
    console.print(f"  Profile: [cyan]{plan.profile}[/]")

    if plan.actions:
        # NOTE: deliberate exception — per-cell status colors (done/skipped/failed)
        # are beyond console_styles.table's single brand column style.
        table = RichTable(title="Actions", box=None)
        table.add_column("Status")
        table.add_column("Component")
        table.add_column("Description")
        for action in plan.actions:
            icon = {"pending": "·", "done": "✓", "skipped": "-", "failed": "✗"}.get(
                action.status, "·"
            )
            style = {"done": "green", "skipped": "yellow", "failed": "red"}.get(
                action.status, "white"
            )
            table.add_row(
                Text(icon, style=style),
                Text(action.component_name, style="bold"),
                action.description,
            )
        console.print(table)

    if plan.dependencies:
        console.print(f"\n[bold]Dependencies:[/] {', '.join(plan.dependencies)}")

    if plan.warnings:
        console.print("\n[bold yellow]Warnings:[/]")
        for w in plan.warnings:
            console.print(f"  ⚠ {w}")


def _execute_plan(
    plan: Any,
    agents: list[str],
    tdd_mode: str = "ask",
    root: str = ".",
    max_tokens: int = 3000,
    sdd_profile: str = "default",
    orchestrator_profile: str | None = None,
    execution_mode: str = "auto",
    artifact_mode: str = "hybrid",
) -> None:
    """Execute the install plan and leave SDD/TDD ready for selected agents."""
    store = UserConfigStore()
    prefs = store.load()

    # Apply profile defaults
    from opencontext_core.setup.presets import PROFILE_CATALOG

    profile_def = PROFILE_CATALOG.get(plan.profile)
    if profile_def:
        prefs.security_mode = profile_def.security_mode
        for key, value in profile_def.features_defaults.items():
            if hasattr(prefs.features, key):
                setattr(prefs.features, key, value)
        prefs.first_run = False

    # Apply component-specific settings
    component_feature_map = {
        "knowledge-graph": ("features", "knowledge_graph"),
        "call-graph": ("features", "call_graph"),
        "learning": ("features", "learning_system"),
        "governance": ("features", "governance"),
        "mcp-server": ("features", "mcp_server"),
        "git-integration": ("features", "git_integration"),
        "embeddings": ("features", "embeddings"),
        "semantic-search": ("features", "semantic_search"),
    }

    for cid in plan.components:
        if cid in component_feature_map:
            section, field = component_feature_map[cid]
            if section == "features":
                setattr(prefs.features, field, True)

    prefs.active_agent = agents[0] if agents else "opencode"
    prefs.sdd_tdd_mode = tdd_mode
    prefs.sdd_token_budget = max_tokens
    prefs.sdd_model_profile = sdd_profile
    prefs.sdd.orchestrator_profile = orchestrator_profile or "opencontext"
    prefs.sdd.execution_mode = execution_mode
    prefs.sdd.artifact_mode = artifact_mode
    prefs.setup_completed = True
    for known_agent in list(prefs.agent_integrations):
        prefs.agent_integrations[known_agent] = known_agent in agents
    for selected_agent in agents:
        prefs.agent_integrations[selected_agent] = True
    store.save(prefs)
    plan.actions = [
        a
        if a.status == "skipped"
        else InstallAction(a.type, a.component_id, a.component_name, a.description, status="done")
        for a in plan.actions
    ]

    root_path = __import__("pathlib").Path(root)

    # ── Agent integrations ─────────────────────────────────────
    generated_files: list[Any] = []
    agent_warnings: list[str] = []
    with console.status("Configuring agent integrations..."):
        from opencontext_core.adapters.agent_manifest import _base_rules, _orchestrator_section

        def _instructions(client: str) -> str:
            return _base_rules() + _orchestrator_section(client)

        known_agents = [a for a in agents if a in KNOWN_AGENTS]
        agent_warnings.extend(
            f"Unknown project-local agent target: {a}" for a in agents if a not in KNOWN_AGENTS
        )
        if known_agents:
            report = Configurator(root_path, instructions_builder=_instructions).configure(
                known_agents, scope="local"
            )
            for entry in report.get("results", []):
                generated_files.extend(entry.get("files", []))

        if "mcp-server" in plan.components or "knowledge-graph" in plan.components:
            global_targets = []
            for selected_agent in agents:
                try:
                    global_targets.append(GlobalAgentTarget(selected_agent))
                except ValueError:
                    continue
            if global_targets:
                AgentInstaller(project_root=root_path).install(
                    targets=global_targets, location="global", yes=True
                )

    # ── SDD/TDD context ─────────────────────────────────────────
    sdd_context = None
    sdd_files: list[Any] = []
    skill_generated = False
    skill_target = root_path / ".opencontext" / "skills" / "opencontext-agent" / "SKILL.md"
    with console.status("Writing SDD/TDD context..."):
        sdd_context, sdd_files = write_sdd_context(
            root_path,
            token_budget_per_phase=max_tokens,
            tdd_mode=tdd_mode,
            active_clients=agents,
            sdd_model_profile=sdd_profile,
            execution_mode=execution_mode,
            artifact_mode=artifact_mode,
        )
        skill_source = (
            __import__("pathlib").Path(__file__).resolve().parent.parent.parent
            / "packages"
            / "opencontext_core"
            / "opencontext_core"
            / "skills"
            / "templates"
            / "opencontext-agent"
            / "SKILL.md"
        )
        if skill_source.exists():
            skill_target.parent.mkdir(parents=True, exist_ok=True)
            skill_target.write_text(skill_source.read_text(encoding="utf-8"), encoding="utf-8")
            skill_generated = True

    # ── Project index ───────────────────────────────────────────
    index_status: dict[str, Any] = {}
    with console.status("Indexing project..."):
        try:
            manifest = OpenContextRuntime().index_project(root_path)
            index_status = {"files": len(manifest.files), "symbols": len(manifest.symbols)}
        except Exception as exc:  # pragma: no cover - defensive, surfaced to user
            index_status = {"error": str(exc)}

    # ── Summary ─────────────────────────────────────────────────────────
    for w in agent_warnings:
        console.warning(w)

    strict_tdd = getattr(sdd_context, "strict_tdd", False) if sdd_context else False
    index_line = (
        f"[red]✗ {index_status['error']}[/]"
        if "error" in index_status
        else f"{index_status.get('files', '?')} files, {index_status.get('symbols', '?')} symbols"
    )
    summary_rows = [
        f"  [bold]Agents:[/]   {', '.join(agents)} ({len(generated_files)} file(s))",
        f"  [bold]SDD/TDD:[/]  {len(sdd_files)} artifact(s), strict TDD: "
        f"{strict_tdd}, mode: {tdd_mode}",
        f"  [bold]Index:[/]    {index_line}",
    ]
    if skill_generated:
        summary_rows.append(f"  [bold]Skill:[/]    {skill_target}")

    console.panel(
        "\n".join(summary_rows),
        title="[bold green]Setup applied[/bold green]",
        style="success",
        fit=True,
    )
