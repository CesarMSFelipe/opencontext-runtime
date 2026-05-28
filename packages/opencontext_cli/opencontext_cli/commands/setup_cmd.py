"""Setup CLI command — interactive setup with presets, profiles, and dry-run."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from opencontext_core.adapters.agent_manifest import AgentIntegrationGenerator, AgentTarget
from opencontext_core.agent_installer import AgentInstaller
from opencontext_core.agent_installer import AgentTarget as GlobalAgentTarget
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

console = Console()


def _wizard_clear(
    step: int,
    total: int,
    context: list[tuple[str, str]] | None = None,
) -> None:
    """Clear the terminal and render a compact wizard step header."""
    try:
        console.clear()
    except Exception:
        pass

    dots = "  ".join(
        "[bold #00C9A7]●[/]" if i <= step else "[dim]○[/]" for i in range(1, total + 1)
    )
    console.print(
        f"\n  [bold white]OpenContext Setup[/bold white]   {dots}   [dim]step {step}/{total}[/dim]"
    )
    if context:
        crumbs = "   [dim]•[/dim]   ".join(f"[dim]{k}:[/dim] [bold]{v}[/bold]" for k, v in context)
        console.print(f"  {crumbs}")
    console.print()


def _check_first_run() -> bool:
    """Check if this is a first run and suggest onboard if so."""
    store = UserConfigStore()
    prefs = store.load()
    if prefs.first_run:
        console.print()
        console.print(
            Panel.fit(
                "[bold yellow]First Run Detected[/bold yellow]\n"
                "It looks like you haven't run [bold]opencontext install[/bold] yet.\n"
                "For a complete project setup in one step, run:\n\n"
                "  [bold cyan]opencontext install[/bold cyan]\n\n"
                "This will auto-detect your project, create your config, index your code,\n"
                "and configure SDD/TDD, agent integrations, and the harness workflow.",
                border_style="yellow",
            )
        )
        return True
    return False


def add_setup_parser(subparsers: Any) -> None:
    """Add setup command parser."""

    setup_parser = subparsers.add_parser(
        "setup", help="Interactive or automated setup with presets and profiles."
    )
    setup_parser.add_argument(
        "--preset",
        choices=["full", "minimal", "enterprise", "air-gapped"],
        help="Preset to install (skips interactive selection).",
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
        choices=["solo-compact", "multi-phase", "subagent-native"],
        default=None,
        help="Orchestration strategy for SDD agents.",
    )


def handle_setup(args: Any) -> None:
    """Handle setup command."""

    preset = getattr(args, "preset", None)
    profile = getattr(args, "profile", None)
    components = getattr(args, "components", None)
    dry_run = getattr(args, "dry_run", False)
    non_interactive = getattr(args, "non_interactive", False)
    agents = _parse_agents(getattr(args, "agent", None))
    tdd_mode = getattr(args, "tdd", "ask")
    root = getattr(args, "root", ".")
    max_tokens = getattr(args, "max_tokens", 3000)
    sdd_profile = getattr(args, "sdd_profile", None)
    orchestrator_profile = getattr(args, "orchestrator_profile", None)

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
        )


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
) -> None:
    """Run interactive setup with rich prompts."""

    # ── Step 1: Preset ──────────────────────────────────────────────────
    if not preset:
        _wizard_clear(1, 6)
        preset = _choose_preset()

    # ── Step 2: Profile ─────────────────────────────────────────────────
    if not profile:
        _wizard_clear(2, 6, [("preset", preset)])
        profile = _choose_profile(preset)

    # ── Step 3: Components ──────────────────────────────────────────────
    if not components:
        _wizard_clear(3, 6, [("preset", preset), ("profile", profile)])
        components = resolve_preset_components(preset)
        console.print(f"[bold]Components ({len(components)}):[/]")
        for c in components:
            console.print(f"  • {c}")
        if not Confirm.ask("\nContinue with these components?", default=True):
            custom_components = _choose_components()
            if custom_components:
                components = custom_components

    # ── Step 4: Agent clients + TDD mode ────────────────────────────────
    _wizard_clear(
        4,
        6,
        [("preset", preset), ("profile", profile), ("components", str(len(components)))],
    )
    agents = _choose_agents(agents)
    tdd_mode = _choose_tdd_mode(tdd_mode)

    # ── Step 5: SDD model profile ────────────────────────────────────────
    if not sdd_profile:
        _wizard_clear(
            5,
            6,
            [("preset", preset), ("profile", profile), ("tdd", tdd_mode)],
        )
        sdd_profile = _choose_sdd_profile()

    # ── Step 6: Plan review + confirm ────────────────────────────────────
    _wizard_clear(
        6,
        6,
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
        console.print("\n[bold yellow]── Dry run — no changes made ──[/]")
        return

    if not Confirm.ask("\nApply this plan?", default=True):
        console.print("[yellow]Setup cancelled.[/]")
        return

    # ── Execute (spinners) ───────────────────────────────────────────────
    try:
        console.clear()
    except Exception:
        pass
    _execute_plan(plan, agents, tdd_mode, root, max_tokens, sdd_profile, orchestrator_profile)
    console.print()
    console.print(
        Panel.fit(
            "[bold green]✓ Setup Complete[/bold green]\n"
            "OpenContext SDD/TDD, graph, memory, and selected agents are ready.",
            border_style="green",
        )
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
) -> None:
    """Run automated setup (non-interactive)."""

    # Check first run — suggest onboard before proceeding
    _check_first_run()

    if not preset and not components:
        preset = "minimal"

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
    )
    console.print("[green]✓ Setup complete.[/]")


def _choose_preset() -> str:
    """Interactive preset selection."""

    presets = get_available_presets()

    console.print("\n[bold]Available Presets:[/]")
    table = Table(box=None)
    table.add_column("Option", style="cyan")
    table.add_column("Preset", style="bold")
    table.add_column("Description")
    table.add_column("Components")

    for i, p in enumerate(presets, 1):
        components = resolve_preset_components(p.id)
        table.add_row(
            str(i),
            p.name,
            p.description,
            ", ".join(components),
        )
    console.print(table)

    choice = Prompt.ask(
        "\nSelect preset",
        choices=[str(i) for i in range(1, len(presets) + 1)],
        default="1",
    )
    return presets[int(choice) - 1].id


def _choose_profile(preset: str | None = None) -> str:
    """Interactive profile selection."""

    profiles = get_available_profiles()

    # Suggest a default based on preset
    suggestions = {
        "full": "developer",
        "minimal": "minimal",
        "enterprise": "security-officer",
        "air-gapped": "security-officer",
    }
    default = suggestions.get(preset or "", "developer")
    default_idx = next((i for i, p in enumerate(profiles) if p.id == default), 0)

    console.print("\n[bold]Available Profiles:[/]")
    for i, p in enumerate(profiles, 1):
        marker = " (recommended)" if p.id == default else ""
        console.print(f"  {i}. {p.name} — {p.description}{marker}")

    choice = Prompt.ask(
        "\nSelect profile",
        choices=[str(i) for i in range(1, len(profiles) + 1)],
        default=str(default_idx + 1),
    )
    return profiles[int(choice) - 1].id


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
    console.print("\n[bold]Agent clients to configure:[/]")
    for agent in supported:
        enabled = agent in selected
        if Confirm.ask(f"  Enable {agent}?", default=enabled):
            if agent not in selected:
                selected.append(agent)
        elif agent in selected:
            selected.remove(agent)
    return selected or ["opencode"]


def _choose_tdd_mode(default: str) -> str:
    modes = ["ask", "strict", "off"]
    labels = {
        "ask": "ask — agent asks per change (recommended)",
        "strict": "strict — tests first whenever a harness exists",
        "off": "off — SDD still works but TDD is optional",
    }
    console.print("\n[bold]TDD behavior:[/]")
    for i, mode in enumerate(modes, 1):
        marker = " (default)" if mode == default else ""
        console.print(f"  {i}. {labels[mode]}{marker}")
    choice = Prompt.ask(
        "Select TDD mode",
        choices=[str(i) for i in range(1, len(modes) + 1)],
        default=str(modes.index(default) + 1 if default in modes else 1),
    )
    return modes[int(choice) - 1]


def _choose_sdd_profile() -> str:
    profiles = ["default", "cheap", "hybrid", "premium"]
    labels = {
        "default": "default — use one model for all phases",
        "cheap": "cheap — fast/free models for exploration, premium for design/verify",
        "hybrid": "hybrid — mix of cheap and premium models per phase",
        "premium": "premium — strongest models for all phases",
    }
    console.print("\n[bold]SDD model profile:[/]")
    for i, p in enumerate(profiles, 1):
        marker = " (recommended)" if p == "cheap" else ""
        console.print(f"  {i}. {labels[p]}{marker}")
    choice = Prompt.ask(
        "Select SDD model profile",
        choices=[str(i) for i in range(1, len(profiles) + 1)],
        default="1",
    )
    return profiles[int(choice) - 1]


def _choose_components() -> list[str]:
    """Interactive component selection."""

    components = get_available_components()
    selected: list[str] = []

    console.print("\n[bold]Select Components:[/]")
    console.print("  (y = yes, n = no, press Enter to finish)")

    for comp in components:
        if Confirm.ask(f"  Install {comp.name}?", default=False):
            selected.append(comp.id)

    return selected


def _show_plan(plan: Any) -> None:
    """Display the install plan."""

    from rich.table import Table as RichTable

    console.print("\n[bold]── Install Plan ──[/]")
    console.print(f"  Preset: [cyan]{plan.preset}[/]")
    console.print(f"  Profile: [cyan]{plan.profile}[/]")

    if plan.actions:
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
    prefs.sdd.orchestrator_profile = orchestrator_profile or prefs.sdd.orchestrator_profile
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

    # ── Phase 1: Agent integrations ─────────────────────────────────────
    generated_files: list = []
    agent_warnings: list[str] = []
    with console.status("[cyan]Configuring agent integrations...[/]", spinner="dots"):
        generator = AgentIntegrationGenerator()
        for selected_agent in agents:
            try:
                generated_files.extend(
                    generator.generate(root_path, target=AgentTarget(selected_agent), force=True)
                )
            except ValueError:
                agent_warnings.append(f"Unknown project-local agent target: {selected_agent}")

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

    # ── Phase 2: SDD/TDD context ─────────────────────────────────────────
    sdd_context = None
    sdd_files: list = []
    skill_generated = False
    skill_target = root_path / ".opencontext" / "skills" / "opencontext-agent" / "SKILL.md"
    with console.status("[cyan]Writing SDD/TDD context...[/]", spinner="dots"):
        sdd_context, sdd_files = write_sdd_context(
            root_path,
            token_budget_per_phase=max_tokens,
            tdd_mode=tdd_mode,
            active_clients=agents,
            sdd_model_profile=sdd_profile,
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

    # ── Phase 3: Project index ───────────────────────────────────────────
    index_status: dict = {}
    with console.status("[cyan]Indexing project...[/]", spinner="dots"):
        try:
            manifest = OpenContextRuntime().index_project(root_path)
            index_status = {"files": len(manifest.files), "symbols": len(manifest.symbols)}
        except Exception as exc:  # pragma: no cover - defensive, surfaced to user
            index_status = {"error": str(exc)}

    # ── Summary ─────────────────────────────────────────────────────────
    for w in agent_warnings:
        console.print(f"[yellow]⚠ {w}[/]")

    strict_tdd = getattr(sdd_context, "strict_tdd", False) if sdd_context else False
    index_line = (
        f"[red]✗ {index_status['error']}[/]"
        if "error" in index_status
        else f"{index_status.get('files', '?')} files, {index_status.get('symbols', '?')} symbols"
    )
    summary_rows = [
        f"  [bold]Agents:[/]   {', '.join(agents)} ({len(generated_files)} file(s))",
        f"  [bold]SDD/TDD:[/]  {len(sdd_files)} artifact(s), strict TDD: {strict_tdd}, mode: {tdd_mode}",
        f"  [bold]Index:[/]    {index_line}",
    ]
    if skill_generated:
        summary_rows.append(f"  [bold]Skill:[/]    {skill_target}")

    console.print(
        Panel.fit(
            "\n".join(summary_rows),
            title="[bold green]Setup applied[/bold green]",
            border_style="green",
        )
    )
