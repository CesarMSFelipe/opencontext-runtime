"""Setup CLI command — interactive setup with presets, profiles, and dry-run."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from opencontext_core.setup.presets import (
    get_available_components,
    get_available_presets,
    get_available_profiles,
    resolve_preset_components,
)
from opencontext_core.setup.plan import build_plan
from opencontext_core.user_prefs import UserConfigStore, UserFeatures, UserPreferences
from opencontext_core.wizard import run_wizard

console = Console()


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
        default="opencode",
        help="Agent to configure (default: opencode).",
    )


def handle_setup(args: Any) -> None:
    """Handle setup command."""

    preset = getattr(args, "preset", None)
    profile = getattr(args, "profile", None)
    components = getattr(args, "components", None)
    dry_run = getattr(args, "dry_run", False)
    non_interactive = getattr(args, "non_interactive", False)
    agent = getattr(args, "agent", "opencode")

    if non_interactive:
        _run_automated(preset, profile, components, dry_run, agent)
    else:
        _run_interactive(preset, profile, components, dry_run, agent)


def _run_interactive(
    preset: str | None,
    profile: str | None,
    components: list[str] | None,
    dry_run: bool,
    agent: str,
) -> None:
    """Run interactive setup with rich prompts."""

    console.print()
    console.print(Panel.fit(
        "[bold]OpenContext Setup[/bold]\n"
        "Configure your environment with presets, profiles, and components.",
        border_style="cyan",
    ))

    # Step 1: Choose preset
    if not preset:
        preset = _choose_preset()
    else:
        console.print(f"[bold]Preset:[/] {preset}")

    # Step 2: Choose profile
    if not profile:
        profile = _choose_profile(preset)
    else:
        console.print(f"[bold]Profile:[/] {profile}")

    # Step 3: Show components (optional override)
    if not components:
        components = resolve_preset_components(preset)
        console.print(f"\n[bold]Components ({len(components)}):[/]")
        for c in components:
            console.print(f"  • {c}")

        if not Confirm.ask("\nContinue with these components?", default=True):
            custom_components = _choose_components()
            if custom_components:
                components = custom_components

    # Step 4: Build plan
    plan = build_plan(
        preset_id=preset,
        profile_id=profile,
        components=components,
    )

    # Step 5: Show plan
    _show_plan(plan)

    if dry_run:
        console.print("\n[bold yellow]── Dry run — no changes made ──[/]")
        return

    # Step 6: Confirm
    if not Confirm.ask("\nApply this plan?", default=True):
        console.print("[yellow]Setup cancelled.[/]")
        return

    # Step 7: Execute
    _execute_plan(plan, agent)
    console.print()
    console.print(Panel.fit(
        "[bold green]✓ Setup Complete[/bold green]\n"
        "Run [bold]opencontext sync[/bold] to activate all changes.",
        border_style="green",
    ))


def _run_automated(
    preset: str | None,
    profile: str | None,
    components: list[str] | None,
    dry_run: bool,
    agent: str,
) -> None:
    """Run automated setup (non-interactive)."""

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

    _execute_plan(plan, agent)
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
    default_idx = next(
        (i for i, p in enumerate(profiles) if p.id == default), 0
    )

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
            icon = {"pending": "·", "done": "✓", "skipped": "−", "failed": "✗"}.get(
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


def _execute_plan(plan: Any, agent: str) -> None:
    """Execute the install plan."""

    from opencontext_core.user_prefs import UserConfigStore
    from rich.progress import Progress, SpinnerColumn, TextColumn

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

    store.save(prefs)
    plan.actions = [
        a if a.status == "skipped" else InstallAction(
            a.type, a.component_id, a.component_name,
            a.description, status="done"
        )
        for a in plan.actions
    ]

    # Handle MCP setup
    if "mcp-server" in plan.components and agent == "opencode":
        console.print("\n[yellow]Configuring MCP for OpenCode...[/]")
        try:
            from opencontext_cli.main import _setup_mcp_for_opencode
            _setup_mcp_for_opencode()
            console.print("[green]✓ MCP configured[/]")
        except ImportError:
            console.print("[yellow]⚠ MCP setup skipped (CLI not available)[/]")

    console.print("[green]✓ Plan applied.[/]")


# Re-export InstallAction for the filter above
from opencontext_core.setup.plan import InstallAction
