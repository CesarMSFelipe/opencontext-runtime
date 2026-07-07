"""Interactive configuration wizard for OpenContext.

Guides users through setup with choices for features, security,
providers, and plugins. Uses rich for a modern interactive TUI.
"""

from __future__ import annotations

from pathlib import Path

from rich.table import Table

from opencontext_core import prompts
from opencontext_core.config import SecurityMode
from opencontext_core.dx.console_styles import console
from opencontext_core.dx.wizard_frame import WizardStep, render_frame
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

# Detail cards for every config-wizard section — the shared wizard frame renders
# these in the config-TUI info-pane format (Current/Effect/Recommended/Risk/CLI).
_CONFIG_WIZARD_STEPS: dict[str, WizardStep] = {
    "security": WizardStep(
        title="Security & privacy",
        effect="Sets the security posture; air_gapped also disables network features.",
        recommended="private_project for local work.",
        risk="Lower postures may allow more external integrations.",
        cli="opencontext config set security_mode <mode>",
    ),
    "features": WizardStep(
        title="Features",
        effect="Enables KG, call graph, learning, governance, embeddings, MCP, git.",
        recommended="Knowledge Graph on.",
        risk="More features can add indexing work.",
        cli="opencontext config set features.<name> <true|false>",
    ),
    "tokens": WizardStep(
        title="Token budgets",
        effect="Caps context size per operation and the max input tokens.",
        recommended="8k-16k budget for normal repos.",
        risk="Too low can hide needed evidence.",
        cli="opencontext config set default_token_budget <n>",
    ),
    "agents": WizardStep(
        title="Agent integrations",
        effect="Marks which AI agents OpenContext integrates with.",
        recommended="Only the agents you actually use.",
        risk="Integration files are written by install/setup, not by this toggle.",
        cli="opencontext install --agent <agent>",
    ),
    "plugins": WizardStep(
        title="Plugins",
        effect="Installs registry plugins and sets plugin auto-update preferences.",
        recommended="Keep minimal until a workflow needs a plugin.",
        risk="Third-party plugins extend the local tool surface.",
        cli="opencontext plugin install <name>",
    ),
    "learning": WizardStep(
        title="Learning & optimization",
        effect="Toggles auto token-budget optimization and anonymous usage stats.",
        recommended="Auto-optimize on; share stats only if you opt in.",
        risk="Sharing sends anonymized usage counters only.",
        cli="opencontext config set auto_optimize <true|false>",
    ),
}


def _ask_bool(question: str, default: bool = True) -> bool:
    """Ask a yes/no question with a navigable Yes/No selector."""

    return prompts.confirm(question, default=default)


def _ask_choice(question: str, choices: list[str], default: int = 0) -> str:
    """Ask user to choose from a list with an arrow-key selector."""

    default_value = choices[default] if 0 <= default < len(choices) else choices[0]
    return str(prompts.select(question, list(choices), default=default_value))


def _ask_int(question: str, default: int, min_val: int = 1, max_val: int = 1000000) -> int:
    """Ask for an integer value via the shared prompt primitives."""

    return prompts.int_input(question, default=default, min_value=min_val, max_value=max_val)


def _print_section(title: str) -> None:
    """Print a brand section header."""

    console.section(title)


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
        # NOTE: deliberate exception — headerless list layout with per-column
        # styling that console_styles.table (titled, uniform style) can't render.
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
            table.add_row("", name, f"v{version}", plug.description[:55], status)

        console.print(table)

    # Ask which plugins to install — one checkbox, not N sequential yes/no prompts.
    choices = [
        (plug.name, f"{plug.name} — {plug.description[:50]}")
        for plug in available
        if plug.name not in installed
    ]
    to_install = list(prompts.checkbox("Select plugins to install", choices)) if choices else []

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
        import sys

        print(
            "opencontext config wizard --non-interactive is not supported.\n"
            "To configure OpenContext non-interactively use:\n"
            "  opencontext config set <key> <value>   # set individual keys\n"
            "  edit opencontext.yaml directly          # full config control",
            file=sys.stderr,
        )
        raise SystemExit(2)

    def _frame(step_index: int, key: str, current: str = "") -> None:
        """Shared wizard frame per section (brand logo + status + detail card)."""
        card = _CONFIG_WIZARD_STEPS[key]
        if current:
            card = card.with_current(current)
        render_frame(step_index, len(_CONFIG_WIZARD_STEPS), card)

    _print_section("OpenContext Configuration Wizard")
    console.print("\nWelcome! Let's set up OpenContext for your workflow.")
    console.print("You can re-run this anytime with: opencontext config wizard")

    _frame(1, "security", prefs.security_mode or "not set")
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

    # One multi-select instead of a long yes/no chain. Network features are
    # hidden (and stay off) in air-gapped mode.
    feature_opts: list[tuple[str, str]] = [
        ("knowledge_graph", "Knowledge Graph (code indexing & search)"),
        ("call_graph", "Call Graph (function call analysis)"),
        ("learning_system", "Learning System (auto-optimize token usage)"),
        ("governance", "Governance (audit trails & policies)"),
    ]
    if not air_gapped:
        feature_opts += [
            ("embeddings", "Embeddings (semantic search)"),
            ("mcp_server", "MCP Server (agent integration)"),
        ]
    feature_opts.append(("git_integration", "Git Integration (context from git history)"))

    enabled_defaults = [key for key, _ in feature_opts if getattr(prefs.features, key)]
    _frame(2, "features", f"{len(enabled_defaults)} of {len(feature_opts)} enabled")
    selected = set(prompts.checkbox("Enable features", feature_opts, defaults=enabled_defaults))
    for key, _ in feature_opts:
        setattr(prefs.features, key, key in selected)

    _frame(
        3,
        "tokens",
        f"budget {prefs.default_token_budget} · max input {prefs.max_input_tokens}",
    )
    console.print("\nConfigure default token limits:")

    prefs.default_token_budget = _ask_int(
        "Default token budget per operation", prefs.default_token_budget, 1000, 100000
    )
    prefs.max_input_tokens = _ask_int("Max input tokens", prefs.max_input_tokens, 1000, 200000)

    # Step 4: Agent Integrations
    if prefs.context_first_mode:
        _print_section("Step 4: Agent Integrations")
        console.print("[dim]Skipped (context-first mode)[/dim]")
    else:
        agent_keys = list(prefs.agent_integrations.keys())
        defaults = [a for a in agent_keys if prefs.agent_integrations[a]]
        _frame(4, "agents", ", ".join(defaults) or "none")
        selected = set(
            prompts.checkbox("Which AI agents do you use?", agent_keys, defaults=defaults)
        )
        for agent in agent_keys:
            prefs.agent_integrations[agent] = agent in selected

    # Step 5: Plugins
    if prefs.context_first_mode:
        _print_section("Step 5: Plugins")
        console.print("[dim]Skipped (context-first mode)[/dim]")
    else:
        _frame(5, "plugins")
        _plugin_wizard_step(prefs)

    # Step 6: Learning & Analytics
    _frame(6, "learning", f"auto-optimize {'on' if prefs.learning_auto_optimize else 'off'}")

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

    def _frame_section(key: str, current: str = "") -> None:
        """One-section rerun still carries the shared wizard frame (Step 1/1)."""
        card = _CONFIG_WIZARD_STEPS[key]
        if current:
            card = card.with_current(current)
        render_frame(1, 1, card)

    if section == "security":
        current = (
            _SECURITY_MODE_CHOICES.index(prefs.security_mode)
            if prefs.security_mode in _SECURITY_MODE_CHOICES
            else _SECURITY_MODE_CHOICES.index(SecurityMode.PRIVATE_PROJECT.value)
        )
        _frame_section("security", str(getattr(prefs, "security_mode", "") or ""))
        prefs.security_mode = _ask_choice(
            "Security mode:",
            _SECURITY_MODE_CHOICES,
            current,
        )
    elif section == "features":
        feature_opts = [
            ("knowledge_graph", "Knowledge Graph"),
            ("call_graph", "Call Graph"),
            ("learning_system", "Learning System"),
        ]
        enabled = [key for key, _ in feature_opts if getattr(prefs.features, key)]
        _frame_section("features", f"{len(enabled)} of {len(feature_opts)} enabled")
        selected = set(prompts.checkbox("Features", feature_opts, defaults=enabled))
        for key, _ in feature_opts:
            setattr(prefs.features, key, key in selected)
    elif section == "tokens":
        _frame_section("tokens", f"budget {prefs.default_token_budget}")
        prefs.default_token_budget = _ask_int("Token budget", prefs.default_token_budget)
    elif section == "agents":
        agent_keys = list(prefs.agent_integrations.keys())
        defaults = [a for a in agent_keys if prefs.agent_integrations[a]]
        _frame_section("agents", ", ".join(defaults) or "none")
        selected = set(prompts.checkbox("Agent integrations", agent_keys, defaults=defaults))
        for agent in agent_keys:
            prefs.agent_integrations[agent] = agent in selected
    elif section == "plugins":
        _frame_section("plugins")
        _plugin_wizard_step(prefs)
    else:
        console.print(f"Unknown section: {section}")
        console.print("Available: security, features, tokens, agents, plugins")
        return

    store.save(prefs)
    console.print(f"\n{section} configuration updated.")


def show_config(root: Path | None = None) -> None:
    """Display current configuration.

    Parameters
    ----------
    root:
        Optional project root to resolve ``opencontext.yaml`` from.  When
        ``None`` the current working directory is used.  If no
        ``opencontext.yaml`` is found a graceful "no project config" line is
        emitted instead of a section header with keys.
    """
    from opencontext_core.dx.console_styles import BRAND_PRIMARY

    store = UserConfigStore()
    prefs = store.load()

    def _flag(value: bool, on: str = "ON", off: str = "OFF") -> str:
        return f"[green]{on}[/]" if value else f"[dim]{off}[/]"

    def _label(text: str) -> None:
        console.print(f"\n  [bold {BRAND_PRIMARY}]{text}[/]")

    # Canonical brand header (logo + brand panel) — replaces the ad-hoc cyan rule.
    console.header("Current Configuration")
    console.print(f"\n  Config file: {store.CONFIG_FILE}")
    # "First run" must agree with reality: once a project opencontext.yaml exists
    # (or an install date is recorded), it is no longer a first run — otherwise
    # `config show` says "First run: Yes" on an initialized, ready project.
    _yaml_present = (
        (Path(root) if root is not None else Path.cwd()) / "opencontext.yaml"
    ).is_file()
    _is_first_run = prefs.first_run and not _yaml_present and not prefs.install_date
    console.print(f"  First run: {'Yes' if _is_first_run else 'No'}")
    if prefs.install_date:
        console.print(f"  Installed: {prefs.install_date}")

    console.print(f"\n  Security Mode: {prefs.security_mode}")
    console.print(f"  Data Classification: {prefs.data_classification}")

    _label("Features")
    for key, value in vars(prefs.features).items():
        console.print(f"    {key}: {_flag(value)}")

    _label("Token Budgets")
    console.print(f"    Default: {prefs.default_token_budget}")
    console.print(f"    Max Input: {prefs.max_input_tokens}")

    _label("Agents")
    for agent, enabled in prefs.agent_integrations.items():
        console.print(f"    {agent}: {_flag(enabled, 'enabled', 'disabled')}")

    # Show installed plugins from the plugin system
    _label("Plugins")
    try:
        registry = PluginRegistry()
        installed_plugins = registry.discover()
        if installed_plugins:
            for p in installed_plugins:
                status = "[green]✓[/]" if p.enabled else "[dim]○[/]"
                console.print(f"    {status} {p.name} v{p.version} [{p.install_source}]")
        else:
            console.print("    [dim]none installed[/]")
    except Exception:
        console.print("    [dim](error reading plugins)[/]")

    _label("Learning")
    console.print(f"    Auto-optimize: {_flag(prefs.learning_auto_optimize)}")
    console.print(f"    Share anonymous: {_flag(prefs.learning_share_anonymous)}")

    _label("Updates")
    console.print(f"    Check updates: {_flag(prefs.check_updates)}")
    console.print(f"    Auto-update plugins: {_flag(prefs.auto_update_plugins)}")

    # --- Project (opencontext.yaml) section ----------------------------------
    _label("Project (opencontext.yaml)")
    project_root = Path(root) if root is not None else Path.cwd()
    yaml_path = project_root / "opencontext.yaml"
    if not yaml_path.is_file():
        console.print("    [dim]no project config (opencontext.yaml not found)[/]")
    else:
        try:
            import yaml as _yaml

            _loaded = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            raw: dict[str, dict[str, object]] = _loaded or {}
        except Exception as exc:
            console.print(f"    [dim](error reading opencontext.yaml: {exc})[/]")
        else:
            console.print(f"    Config file: {yaml_path}")
            # memory.provider
            memory_cfg = raw.get("memory", {}) or {}
            console.print(f"    memory.provider: {memory_cfg.get('provider', '(not set)')}")
            # storage.mode
            storage_cfg = raw.get("storage", {}) or {}
            console.print(f"    storage.mode: {storage_cfg.get('mode', '(not set)')}")
            # sdd.flow_mode
            sdd_cfg = raw.get("sdd", {}) or {}
            console.print(f"    sdd.flow_mode: {sdd_cfg.get('flow_mode', '(not set)')}")
            # models.roles
            models_cfg = raw.get("models", {}) or {}
            roles = models_cfg.get("roles")
            if roles and isinstance(roles, dict):
                console.print("    models.roles:")
                for _role, _rc in roles.items():
                    if isinstance(_rc, dict):
                        _prov = _rc.get("provider", "?")
                        _model = _rc.get("model", "?")
                        console.print(f"      {_role}: {_prov} / {_model}")
                    else:
                        console.print(f"      {_role}: {_rc}")
            elif roles:
                console.print(f"    models.roles: {roles}")
            else:
                console.print("    models.roles: (not set)")

            # --- Provenance section (layered resolution) ----------------------
            _label("Provenance")
            try:
                from opencontext_core.config_resolver import resolve as _resolve

                resolved = _resolve(project_path=project_root)
                prov = resolved.provenance
                # Show the winning layer for the three key dimensions.
                for dotted_key, top_key in [
                    ("memory.provider", "memory"),
                    ("storage.mode", "storage"),
                    ("sdd.flow_mode", "sdd"),
                ]:
                    layer = prov.layer_of(top_key)
                    console.print(f"    {dotted_key}: [dim]{layer}[/]")
            except Exception as exc:
                # Same leak surface as CONFIG_INVALID: pydantic validation text
                # can echo secret-shaped raw values (`input_value='sk-...'`).
                from opencontext_core.config_explain import redact_secret_input_values

                console.print(
                    f"    [dim](provenance unavailable: {redact_secret_input_values(str(exc))})[/]"
                )


def reset_config() -> None:
    """Reset to factory defaults."""

    if not _ask_bool("Reset ALL configuration to defaults?"):
        console.print("Cancelled.")
        return

    store = UserConfigStore()
    store.reset()
    console.print("Configuration reset to defaults.")
    console.print(f"Config file: {store.CONFIG_FILE}")
