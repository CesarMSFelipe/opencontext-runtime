"""Interactive configuration wizard for OpenContext.

Guides users through setup with choices for features, security,
providers, and plugins. Uses rich for a modern interactive TUI.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from opencontext_core.config import SecurityMode
from opencontext_core.plugin_system import (
    PluginInstaller,
    PluginRegistry,
    RegistryFetcher,
)
from opencontext_core.user_prefs import (
    UserConfigStore,
    UserPreferences,
    mark_setup_complete,
)

# Enum-aligned security choices; deriving from SecurityMode guarantees the
# saved preference is always a value the runtime config can load.
_SECURITY_MODE_CHOICES = [mode.value for mode in SecurityMode]

console = Console()


# ── TUI Menu ────────────────────────────────────────────────────────────────


def run_wizard_menu() -> None:
    """Show interactive menu and delegate to the selected section."""

    while True:
        console.clear()
        menu = Panel(
            "\n".join(
                [
                    "[bold]OpenContext Configuration[/bold]",
                    "",
                    "  [cyan]1[/]  Full configuration wizard",
                    "  [cyan]2[/]  Security & privacy",
                    "  [cyan]3[/]  Features",
                    "  [cyan]4[/]  Token budgets",
                    "  [cyan]5[/]  Agent integrations",
                    "  [cyan]6[/]  Plugins",
                    "  [cyan]7[/]  Show current config",
                    "  [cyan]8[/]  Reset to defaults",
                    "  [cyan]q[/]  Quit",
                    "",
                    "[dim]j/k: navigate • enter: select • q: quit[/]",
                ]
            ),
            title="OpenContext Config",
            border_style="cyan",
            padding=(1, 2),
        )
        console.print(menu)
        console.print()

        choice = Prompt.ask(
            "Select option",
            choices=["1", "2", "3", "4", "5", "6", "7", "8", "q"],
            default="1",
        )

        if choice == "1":
            run_wizard()
        elif choice == "2":
            reconfigure("security")
        elif choice == "3":
            reconfigure("features")
        elif choice == "4":
            reconfigure("tokens")
        elif choice == "5":
            reconfigure("agents")
        elif choice == "6":
            reconfigure("plugins")
        elif choice == "7":
            show_config()
            console.print("\n[dim]Press Enter to return to menu...[/]")
            input()
        elif choice == "8":
            reset_config()
        elif choice == "q":
            console.print("[dim]Goodbye.[/]")
            break


def _ask_bool(question: str, default: bool = True) -> bool:
    """Ask a yes/no question."""

    result = Confirm.ask(f"\n[bold]{question}[/]", default=default)
    return result


def _ask_choice(question: str, choices: list[str], default: int = 0) -> str:
    """Ask user to choose from a list."""

    table = Table(box=None, show_header=False)
    for i, choice in enumerate(choices, 1):
        marker = " (default)" if i - 1 == default else ""
        table.add_row(f"  [cyan]{i}[/]", f"{choice}{marker}")

    console.print(f"\n[bold]{question}[/]")
    console.print(table)

    choice = Prompt.ask(
        "Enter number",
        choices=[str(i) for i in range(1, len(choices) + 1)],
        default=str(default + 1),
    )
    return choices[int(choice) - 1]


def _ask_int(question: str, default: int, min_val: int = 1, max_val: int = 1000000) -> int:
    """Ask for an integer value."""

    result = IntPrompt.ask(
        f"\n[bold]{question}[/]",
        default=default,
    )
    if result < min_val:
        console.print(f"[yellow]Value too low. Using minimum: {min_val}[/]")
        return min_val
    if result > max_val:
        console.print(f"[yellow]Value too high. Using maximum: {max_val}[/]")
        return max_val
    return result


def _print_section(title: str) -> None:
    """Print a section header."""

    console.rule(f"[bold]{title}[/]", style="cyan")


def _plugin_wizard_step(prefs: UserPreferences) -> None:
    """Interactive plugin browser for the setup wizard."""

    registry = PluginRegistry()
    installed = {p.name: p for p in registry.discover()}

    console.print("\nBrowse and install plugins. You can also manage them later with:")
    console.print("  opencontext plugin search | install | remove\n")

    # Fetch available plugins from registry
    fetcher = RegistryFetcher()
    try:
        available = fetcher.fetch()
    except Exception:
        available = fetcher.search()

    if available:
        console.print("[bold]Available plugins:[/]")
        table = Table(box=None, show_header=False)
        table.add_column("")
        table.add_column("Plugin", style="cyan")
        table.add_column("Version")
        table.add_column("Description")
        table.add_column("Status", width=12)

        for plug in available:
            name = plug.name
            version = plug.versions[0].version if plug.versions else "—"
            status = "✓ installed" if name in installed else "—"
            f"  [{len(available)}] " if False else "   "
            table.add_row("", name, f"v{version}", plug.description[:55], status)

        console.print(table)

    # Ask which plugins to install
    to_install = []
    for plug in available:
        name = plug.name
        if name in installed:
            continue
        if _ask_bool(f"Install '{name}'? ({plug.description[:50]})", default=False):
            to_install.append(name)

    # Install selected plugins
    if to_install:
        installer = PluginInstaller(registry)
        console.print()
        for name in to_install:
            console.print(f"  Installing [cyan]{name}[/]...")
            result = installer.install_from_registry(name)
            if result.status == "installed":
                console.print(f"    [green]✓[/] {result.message}")
            elif result.status == "failed":
                console.print(f"    [red]✗[/] {result.message}")
            else:
                console.print(f"    {result.message}")

    # Auto-update preference
    console.print()
    prefs.check_updates = _ask_bool("Check for updates automatically?", prefs.check_updates)
    prefs.auto_update_plugins = _ask_bool("Auto-update plugins?", prefs.auto_update_plugins)


def run_wizard(non_interactive: bool = False, defaults_only: bool = False) -> UserPreferences:
    """Run the configuration wizard.

    Args:
        non_interactive: Skip prompts, use defaults.
        defaults_only: Use defaults but still show summary.

    Returns:
        Configured UserPreferences.
    """

    store = UserConfigStore()
    prefs = store.load()

    if non_interactive:
        mark_setup_complete(prefs)
        store.save(prefs)
        return prefs

    _print_section("OpenContext Configuration Wizard")
    console.print("\nWelcome! Let's set up OpenContext for your workflow.")
    console.print("You can re-run this anytime with: opencontext config wizard")

    # Step 1: Security Mode
    _print_section("Step 1: Security & Privacy")
    console.print("\nChoose your security mode:")
    console.print("  developer        - Local dev posture, fewest restrictions")
    console.print("  private_project  - Local only, no external APIs")
    console.print("  enterprise       - Team sharing with governance")
    console.print("  air_gapped       - Completely offline")

    default_index = _SECURITY_MODE_CHOICES.index(SecurityMode.PRIVATE_PROJECT.value)
    security_choice = _ask_choice(
        "Security mode:",
        _SECURITY_MODE_CHOICES,
        default=default_index,
    )
    prefs.security_mode = security_choice

    air_gapped = security_choice == SecurityMode.AIR_GAPPED.value
    if air_gapped:
        prefs.features.mcp_server = False
        prefs.features.embeddings = False
        prefs.features.semantic_search = False
        console.print("\nAir-gapped mode: disabling network features.")

    # Step 2: Features
    _print_section("Step 2: Features")
    console.print("\nEnable/disable features:")

    prefs.features.knowledge_graph = _ask_bool(
        "Knowledge Graph (code indexing & search)?", prefs.features.knowledge_graph
    )
    prefs.features.call_graph = _ask_bool(
        "Call Graph (function call analysis)?", prefs.features.call_graph
    )
    prefs.features.learning_system = _ask_bool(
        "Learning System (auto-optimize token usage)?", prefs.features.learning_system
    )
    prefs.features.governance = _ask_bool(
        "Governance (audit trails & policies)?", prefs.features.governance
    )

    if not air_gapped:
        prefs.features.embeddings = _ask_bool(
            "Embeddings (semantic search)?", prefs.features.embeddings
        )
        prefs.features.mcp_server = _ask_bool(
            "MCP Server (agent integration)?", prefs.features.mcp_server
        )

    prefs.features.git_integration = _ask_bool(
        "Git Integration (context from git history)?", prefs.features.git_integration
    )

    # Step 3: Token Budgets
    _print_section("Step 3: Token Budgets")
    console.print("\nConfigure default token limits:")

    prefs.default_token_budget = _ask_int(
        "Default token budget per operation", prefs.default_token_budget, 1000, 100000
    )
    prefs.max_input_tokens = _ask_int("Max input tokens", prefs.max_input_tokens, 1000, 200000)

    # Step 4: Agent Integrations
    _print_section("Step 4: Agent Integrations")
    if prefs.context_first_mode:
        console.print("[dim]Skipped (context-first mode)[/dim]")
    else:
        console.print("\nWhich AI agents do you use?")
        for agent, enabled in prefs.agent_integrations.items():
            prefs.agent_integrations[agent] = _ask_bool(f"  Enable {agent}?", enabled)

    # Step 5: Plugins
    _print_section("Step 5: Plugins")
    if prefs.context_first_mode:
        console.print("[dim]Skipped (context-first mode)[/dim]")
    else:
        _plugin_wizard_step(prefs)

    # Step 6: Learning & Analytics
    _print_section("Step 6: Learning & Optimization")

    prefs.learning_auto_optimize = _ask_bool(
        "Auto-optimize token budgets based on usage?", prefs.learning_auto_optimize
    )
    prefs.learning_share_anonymous = _ask_bool(
        "Share anonymous usage stats to improve recommendations?",
        prefs.learning_share_anonymous,
    )

    # Summary
    _print_section("Configuration Summary")
    console.print(f"\n  Security Mode: {prefs.security_mode}")
    console.print(f"  Knowledge Graph: {'ON' if prefs.features.knowledge_graph else 'OFF'}")
    console.print(f"  Call Graph: {'ON' if prefs.features.call_graph else 'OFF'}")
    console.print(f"  Learning System: {'ON' if prefs.features.learning_system else 'OFF'}")
    console.print(f"  MCP Server: {'ON' if prefs.features.mcp_server else 'OFF'}")
    console.print(f"  Token Budget: {prefs.default_token_budget}")
    console.print(f"\n  Agents: {', '.join(a for a, e in prefs.agent_integrations.items() if e)}")

    if not defaults_only:
        confirm = _ask_bool("\nSave this configuration?", True)
        if not confirm:
            console.print("Configuration discarded. Re-run with: opencontext config wizard")
            return store.load()

    mark_setup_complete(prefs)
    store.save(prefs)
    # Mirror runtime-affecting choices into the project config so the wizard
    # actually changes runtime behavior, not just user-prefs.
    from opencontext_core.config_sync import sync_runtime_prefs_to_yaml

    applied = sync_runtime_prefs_to_yaml(prefs)

    console.print("\nConfiguration saved!")
    console.print(f"Location: {store.CONFIG_FILE}")
    if applied:
        console.print(f"Applied to opencontext.yaml: {', '.join(applied)}")
    console.print("\nNext steps:")
    console.print("  1. cd your-project")
    console.print("  2. opencontext install")
    console.print("  3. opencontext index .")

    return prefs


def reconfigure(section: str | None = None) -> None:
    """Re-run wizard for a specific section or all."""

    if section is None:
        run_wizard()
        return

    store = UserConfigStore()
    prefs = store.load()

    if section == "security":
        current = (
            _SECURITY_MODE_CHOICES.index(prefs.security_mode)
            if prefs.security_mode in _SECURITY_MODE_CHOICES
            else _SECURITY_MODE_CHOICES.index(SecurityMode.PRIVATE_PROJECT.value)
        )
        prefs.security_mode = _ask_choice(
            "Security mode:",
            _SECURITY_MODE_CHOICES,
            current,
        )
    elif section == "features":
        prefs.features.knowledge_graph = _ask_bool(
            "Knowledge Graph?", prefs.features.knowledge_graph
        )
        prefs.features.call_graph = _ask_bool("Call Graph?", prefs.features.call_graph)
        prefs.features.learning_system = _ask_bool(
            "Learning System?", prefs.features.learning_system
        )
    elif section == "tokens":
        prefs.default_token_budget = _ask_int("Token budget", prefs.default_token_budget)
    elif section == "agents":
        for agent in prefs.agent_integrations:
            prefs.agent_integrations[agent] = _ask_bool(
                f"{agent}?", prefs.agent_integrations[agent]
            )
    elif section == "plugins":
        _plugin_wizard_step(prefs)
    else:
        console.print(f"Unknown section: {section}")
        console.print("Available: security, features, tokens, agents, plugins")
        return

    store.save(prefs)
    console.print(f"\n{section} configuration updated.")


def show_config() -> None:
    """Display current configuration."""

    store = UserConfigStore()
    prefs = store.load()

    _print_section("Current Configuration")
    console.print(f"\n  Config file: {store.CONFIG_FILE}")
    console.print(f"  First run: {'Yes' if prefs.first_run else 'No'}")
    if prefs.install_date:
        console.print(f"  Installed: {prefs.install_date}")

    console.print(f"\n  Security Mode: {prefs.security_mode}")
    console.print(f"  Data Classification: {prefs.data_classification}")

    console.print("\n  Features:")
    for key, value in vars(prefs.features).items():
        console.print(f"    {key}: {'ON' if value else 'OFF'}")

    console.print("\n  Token Budgets:")
    console.print(f"    Default: {prefs.default_token_budget}")
    console.print(f"    Max Input: {prefs.max_input_tokens}")

    console.print("\n  Agents:")
    for agent, enabled in prefs.agent_integrations.items():
        console.print(f"    {agent}: {'enabled' if enabled else 'disabled'}")

    # Show installed plugins from the plugin system
    try:
        registry = PluginRegistry()
        installed_plugins = registry.discover()
        if installed_plugins:
            console.print(f"\n  Plugins ({len(installed_plugins)} installed):")
            for p in installed_plugins:
                status = "✓" if p.enabled else "○"
                console.print(f"    {status} {p.name} v{p.version} [{p.install_source}]")
        else:
            console.print("\n  Plugins: none installed")
    except Exception:
        console.print("\n  Plugins: (error reading plugins)")

    console.print("\n  Learning:")
    console.print(f"    Auto-optimize: {'ON' if prefs.learning_auto_optimize else 'OFF'}")
    console.print(f"    Share anonymous: {'ON' if prefs.learning_share_anonymous else 'OFF'}")

    console.print("\n  Updates:")
    console.print(f"    Check updates: {'ON' if prefs.check_updates else 'OFF'}")
    console.print(f"    Auto-update plugins: {'ON' if prefs.auto_update_plugins else 'OFF'}")


def reset_config() -> None:
    """Reset to factory defaults."""

    if not _ask_bool("Reset ALL configuration to defaults?"):
        console.print("Cancelled.")
        return

    store = UserConfigStore()
    store.reset()
    console.print("Configuration reset to defaults.")
    console.print(f"Config file: {store.CONFIG_FILE}")
