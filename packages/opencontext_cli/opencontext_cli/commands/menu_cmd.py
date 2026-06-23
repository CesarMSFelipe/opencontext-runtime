"""Main TUI menu for OpenContext.

Run opencontext with no arguments to launch this interactive menu.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from opencontext_cli.commands.update_cmd import handle_upgrade
from opencontext_cli.commands.verified_context_view import (
    gather_kg_status,
    render_kg_header,
    render_verified_context,
)
from opencontext_core import prompts
from opencontext_core.dx.console_styles import console, show_logo
from opencontext_core.update import EcosystemUpdateChecker, UpdateChecker


def _action_header(title: str) -> None:
    """Clear the terminal and show the OpenContext logo + a screen title, so
    every action screen carries the same icon as the home menu."""
    try:
        console.clear()
    except Exception:
        pass
    show_logo(compact=True)
    console.print(f"  [dim]>[/dim] [bold]{title}[/bold]")
    console.print()


def run_main_menu() -> None:
    """Show the main OpenContext menu and delegate to the selected command."""

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        console.print(
            "[yellow]The interactive menu needs a terminal.[/] "
            "Run a subcommand instead, e.g. [cyan]opencontext --help[/]."
        )
        return

    while True:
        try:
            console.clear()
        except Exception:
            pass

        show_logo()
        console.print()
        _print_kg_header()
        console.print()

        _print_update_banner()
        console.print()

        choice = prompts.select(
            "Main menu",
            [
                (None, "Setup"),
                ("install", "Install / reconfigure"),
                ("upgrade", "Upgrade all packages"),
                ("sync", "Re-sync environment"),
                (None, "Configure"),
                ("configure", "Settings (providers, agents, plugins, SDD, features…)"),
                (None, "Tools"),
                ("verified", "Verified context for a task"),
                ("memory", "Context memory"),
                ("doctor", "Doctor"),
                ("backups", "Backups"),
                ("uninstall", "Uninstall"),
                ("quit", "Quit"),
            ],
            default="install",
        )

        if choice == "quit":
            console.print("[dim]Goodbye.[/]")
            break

        actions = {
            "install": _run_install,
            "upgrade": _run_upgrade,
            "sync": _run_sync,
            "configure": run_config_menu,
            "memory": _run_memory_tools,
            "doctor": _run_doctor,
            "backups": _run_backups,
            "uninstall": _run_uninstall,
            "verified": _run_verified_context,
        }
        action = actions.get(choice)
        if action is not None:
            action()

        prompts.pause("Press Enter to return to menu")


def run_config_menu() -> None:
    """Single configuration surface — every setting lives here, one path each.

    Both ``opencontext`` (home menu → Configure) and ``opencontext config`` open
    this same menu, so settings are never split across two places. Section
    actions are reused from the home menu (models/agents/sdd) and from the core
    wizard (security/features/tokens/plugins/show/reset), composed here because
    the CLI may import core but not vice versa.
    """
    from opencontext_core import wizard

    # The loop ends only on "back"; without a terminal the selector returns its
    # default forever, so guard against a non-interactive hang.
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        console.print(
            "[yellow]The configuration menu needs a terminal.[/] "
            "Run [cyan]opencontext config wizard --non-interactive[/] instead."
        )
        return

    def _wrap(title: str, fn: Any) -> Any:
        # Core-wizard actions carry no header of their own; wrap them so every
        # config sub-screen shows the OpenContext logo + title, like the CLI ones.
        def run() -> None:
            _action_header(title)
            fn()

        return run

    actions = {
        "wizard": _wrap("Full setup wizard", wizard.run_wizard),
        "security": _wrap("Security & privacy", lambda: wizard.reconfigure("security")),
        "features": _wrap("Features", lambda: wizard.reconfigure("features")),
        "tokens": _wrap("Token budgets", lambda: wizard.reconfigure("tokens")),
        "models": _run_configure_models,
        "agents": _run_agent_integrations,
        "plugins": _wrap("Plugins", lambda: wizard.reconfigure("plugins")),
        "memory": _run_memory_backend,
        "language": _run_language,
        "sdd": _run_sdd_profiles,
        "show": _wrap("Current configuration", wizard.show_config),
        "reset": _wrap("Reset to defaults", wizard.reset_config),
    }

    while True:
        _action_header("Configuration")
        choice = prompts.select(
            "Configuration",
            [
                (None, "Setup"),
                ("wizard", "Full setup wizard"),
                (None, "Settings"),
                ("security", "Security & privacy"),
                ("features", "Features"),
                ("tokens", "Token budgets"),
                ("models", "Providers & models"),
                ("agents", "Agent integrations"),
                ("plugins", "Plugins"),
                ("memory", "Memory backend"),
                ("language", "Language"),
                ("sdd", "SDD & TDD settings"),
                (None, "Config file"),
                ("show", "Show current config"),
                ("reset", "Reset to defaults"),
                ("back", "Back"),
            ],
            default="wizard",
        )

        if choice == "back":
            break

        action = actions.get(choice)
        if action is not None:
            action()

        prompts.pause("Press Enter to return to configuration")


def _print_update_banner() -> None:
    """Show a one-line update notice if any cached update is available."""
    notices: list[str] = []
    try:
        state = UpdateChecker._load_cache()
        if state.check and state.check.is_outdated:
            notices.append(
                f"opencontext {state.check.current_version} -> {state.check.latest_version}"
            )
    except Exception:
        pass
    try:
        for eco in EcosystemUpdateChecker.check_cached():
            notices.append(f"{eco.name} {eco.current_version} -> {eco.latest_version}")
    except Exception:
        pass
    if notices:
        joined = ", ".join(notices)
        console.print(
            f"  [bold yellow]Updates available:[/] {joined}  "
            "[dim](choose “Upgrade all packages”)[/]"
        )
        console.print()


def _print_kg_header() -> None:
    """Show the knowledge-graph status panel at the top of the menu."""
    try:
        status = gather_kg_status(".")
        console.print(render_kg_header(status))
    except Exception:
        # The header is informational; never block the menu on a status read.
        pass


# ── Menu action dispatchers ─────────────────────────────────────────────


def _run_install() -> None:
    """Start installation — opencontext install."""
    _action_header("Install / Reconfigure")
    try:
        from opencontext_cli.main import _install

        _install(argparse.Namespace(root=".", yes=False))
    except Exception as exc:
        console.print(f"[red]Installation failed: {exc}[/]")


def _run_upgrade() -> None:
    """Upgrade all packages and re-sync the environment."""
    _action_header("Upgrade all packages")
    handle_upgrade(type("Args", (), {})())
    console.print()
    console.print("[dim]Re-syncing environment after upgrade...[/]")
    try:
        from opencontext_cli.commands.sync_cmd import handle_sync

        handle_sync(type("Args", (), {"sync_command": None})())
    except Exception as exc:
        console.print(f"[yellow]Re-sync note: {exc}[/]")


def _run_sync() -> None:
    """Re-sync environment — refresh configs, MCP, and plugin state."""
    _action_header("Re-sync environment")
    try:
        from opencontext_cli.commands.sync_cmd import handle_sync

        handle_sync(type("Args", (), {"sync_command": None})())
    except Exception as exc:
        console.print(f"[red]Sync failed: {exc}[/]")


def _run_configure_models() -> None:
    """Configure the default provider and model (this menu entry's actual job)."""
    _action_header("Providers & models")

    from opencontext_core.user_prefs import UserConfigStore

    store = UserConfigStore()
    prefs = store.load()

    console.print("[bold]Current model configuration:[/]")
    console.print(f"  Default provider: {prefs.default_provider or '[dim]not set[/dim]'}")
    console.print(f"  Default model:    {prefs.default_model or '[dim]not set[/dim]'}")
    console.print()

    known_providers = ["anthropic", "openai", "mock"]
    known_models = {
        "anthropic": ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"],
        "openai": ["gpt-4o", "gpt-4o-mini", "o1"],
        "mock": ["mock-llm"],
    }

    provider = prompts.select(
        "Default provider",
        known_providers,
        default=prefs.default_provider or "anthropic",
    )
    model_choices = known_models.get(provider, [])
    if model_choices:
        model = prompts.select(
            "Default model",
            model_choices,
            default=prefs.default_model
            if prefs.default_model in model_choices
            else model_choices[0],
        )
    else:
        model = prompts.text("Default model", default=prefs.default_model or "")

    prefs.default_provider = provider
    prefs.default_model = model
    store.save(prefs)
    # Bridge to opencontext.yaml — the runtime reads models.default from yaml, so
    # without this the chosen provider/model silently no-op at runtime.
    from opencontext_core.config_sync import sync_runtime_prefs_to_yaml

    sync_runtime_prefs_to_yaml(prefs)
    console.print("[green]✓ Model configuration saved[/]")

    # Per-persona SDD routing: pick the model for each phase (sent to the agent
    # as an MCP sampling hint). Opt-in so the default flow stays one step.
    if prompts.confirm("Also set a model per SDD persona?", default=False):
        _configure_persona_models()


def _configure_persona_models() -> None:
    """Navigable per-persona model routing for SDD phases. Reuses models_cmd."""
    import yaml

    from opencontext_cli.commands import models_cmd
    from opencontext_core.config import find_config

    cfg_path = find_config(".")
    if cfg_path is None:
        console.print(
            "[yellow]No opencontext.yaml found.[/] Run [cyan]opencontext install[/] first."
        )
        return

    model_hints = [
        ("claude-opus-4-8", "opus — strongest"),
        ("claude-sonnet-4-6", "sonnet — balanced"),
        ("claude-haiku-4-5-20251001", "haiku — cheap & fast"),
        ("__default__", "Use the default model"),
        ("__custom__", "Custom model id…"),
    ]

    while True:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        persona_models = (data.get("sdd", {}) or {}).get("persona_models", {}) or {}
        choices: list[Any] = [
            (name, f"{name:12} {phases:18} → {persona_models.get(pid, 'default')}")
            for name, (pid, phases) in models_cmd.PERSONAS.items()
        ]
        choices += [prompts.SEPARATOR, ("__done__", "Done")]

        pick = prompts.select("Model per SDD persona", choices, default="__done__")
        if pick == "__done__":
            break

        hint = prompts.select(f"Model for {pick}", model_hints, default="__default__")
        if hint == "__custom__":
            hint = prompts.text(f"Custom model id for {pick}").strip()
            if not hint:
                continue
        if hint == "__default__":
            # Drop the override so this persona falls back to the default model.
            persona_id = models_cmd.PERSONAS[pick][0]
            sdd = data.setdefault("sdd", {})
            sdd.setdefault("persona_models", {}).pop(persona_id, None)
            cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            console.print(f"[green]✓ {pick} → default[/]")
        else:
            models_cmd._set_persona(cfg_path, pick, hint)


def _run_agent_integrations() -> None:
    """Configure agent integrations — show current state, offer regeneration."""
    _action_header("Agent integrations")

    from pathlib import Path

    from opencontext_core.configurator import KNOWN_AGENTS, Configurator
    from opencontext_core.user_prefs import UserConfigStore

    store = UserConfigStore()
    prefs = store.load()
    configured = getattr(prefs, "agent_integrations", {}) or {}

    console.print("[bold]Configured agents:[/]")
    if configured:
        for agent, enabled in configured.items():
            icon = "[green]●[/]" if enabled else "[dim]○[/]"
            console.print(f"  {icon}  {agent}")
    else:
        console.print("  [dim]None configured yet[/]")
    console.print()

    supported = list(KNOWN_AGENTS)
    enabled_now = [a for a in supported if configured.get(a)]
    targets = prompts.checkbox(
        "Select agents to configure",
        supported,
        defaults=enabled_now,
    )
    if not targets:
        console.print("[dim]No agents selected.[/]")
        return

    # Single engine: merges a managed block into existing files and writes the
    # MCP entry per agent, reversible by `opencontext uninstall`.
    configurator = Configurator(Path("."))
    for target in targets:
        try:
            report = configurator.configure_one(target, "local")
            files = report.get("files", [])
            console.print(f"[green]✓ Configured {len(files)} file(s) for {target}[/]")
            for f in files:
                console.print(f"  [dim]{f}[/]")
            prefs.agent_integrations[target] = True
        except Exception as exc:
            console.print(f"[red]Failed to configure {target}: {exc}[/]")
    store.save(prefs)


def _run_sdd_profiles() -> None:
    """Configure SDD model profile and TDD mode."""
    _action_header("SDD & TDD settings")
    try:
        from opencontext_core.user_prefs import UserConfigStore

        store = UserConfigStore()
        prefs = store.load()

        console.print("[bold]Current settings:[/]")
        console.print(f"  SDD model profile: [cyan]{prefs.sdd.sdd_model_profile or 'default'}[/]")
        console.print(f"  TDD mode:          [cyan]{prefs.sdd.tdd_mode or 'ask'}[/]")
        console.print(f"  Token budget/phase: [cyan]{getattr(prefs, 'sdd_token_budget', 3000)}[/]")
        console.print()

        profile = prompts.select(
            "SDD model profile",
            ["default", "cheap", "hybrid", "premium"],
            default=prefs.sdd.sdd_model_profile or "hybrid",
        )
        tdd = prompts.select(
            "TDD mode",
            ["ask", "strict", "off"],
            default=prefs.sdd.tdd_mode or "ask",
        )
        prefs.sdd.sdd_model_profile = profile
        prefs.sdd.tdd_mode = tdd
        store.save(prefs)
        console.print()
        console.print("[green]✓ SDD & TDD settings saved[/]")
    except Exception as exc:
        console.print(f"[red]Failed: {exc}[/]")


def _run_memory_backend() -> None:
    """Choose the memory backend (local / engram / auto) — writes memory.provider."""
    _action_header("Memory backend")

    from opencontext_core.config import find_config, load_config
    from opencontext_core.config_sync import set_yaml_key

    current = "local"
    cf = find_config(".")
    if cf is not None and cf.exists():
        try:
            current = load_config(cf).memory.provider
        except Exception:
            pass

    console.print(f"[bold]Current backend:[/] [cyan]{current}[/]\n")
    choice = prompts.select(
        "Memory backend",
        [
            ("local", "Local — OpenContext's own engine (layers, decay, recall)"),
            ("engram", "Engram — episodic & semantic → Engram, the rest → OpenContext"),
            ("auto", "Auto — couple with Engram if present, else local"),
        ],
        default=current if current in ("local", "engram", "auto") else "local",
    )
    if set_yaml_key("memory.provider", choice):
        console.print(f"[green]✓ Memory backend set to {choice}[/]")
    else:
        console.print(
            "[yellow]No opencontext.yaml found.[/] Run [cyan]opencontext install[/] first."
        )


def _run_language() -> None:
    """Choose the interface language (en / es) — writes ui_language."""
    _action_header("Language")

    from opencontext_core.config import find_config, load_config
    from opencontext_core.config_sync import set_yaml_key

    current = "en"
    cf = find_config(".")
    if cf is not None and cf.exists():
        try:
            current = getattr(load_config(cf), "ui_language", "en")
        except Exception:
            pass

    console.print(f"[bold]Current language:[/] [cyan]{current}[/]\n")
    choice = prompts.select(
        "Interface language",
        [("en", "English"), ("es", "Español")],
        default=current if current in ("en", "es") else "en",
    )
    if set_yaml_key("ui_language", choice):
        console.print(f"[green]✓ Language set to {choice}[/]")
    else:
        console.print(
            "[yellow]No opencontext.yaml found.[/] Run [cyan]opencontext install[/] first."
        )


def _run_memory_tools() -> None:
    """Context memory — list and search memory entries."""
    _action_header("Context memory")
    try:
        from opencontext_cli.main import _memory

        _memory(argparse.Namespace(memory_command="list", config="opencontext.yaml"))
    except Exception as exc:
        console.print(f"[red]Memory list failed: {exc}[/]")


def _run_doctor() -> None:
    """Run health checks — opencontext doctor."""
    _action_header("Doctor — Health Check")
    try:
        from pathlib import Path

        from opencontext_core.doctor.checks import run_doctor
        from opencontext_core.runtime import OpenContextRuntime

        with console.status("[cyan]Running health checks...[/]", spinner="dots"):
            config_path = Path("opencontext.yaml")
            runtime = OpenContextRuntime(
                config_path=str(config_path) if config_path.exists() else None,
            )
            checks = run_doctor(runtime.config)

        passed = sum(1 for c in checks if getattr(c, "ok", False))
        failed = len(checks) - passed

        console.print(
            f"[bold]Results:[/] {len(checks)} checks  "
            f"[green]{passed} passed[/]  [red]{failed} failed[/]"
        )
        console.print()

        for check in checks:
            ok = getattr(check, "ok", False)
            name = getattr(check, "name", "unknown")
            details = getattr(check, "details", "")
            if ok:
                console.print(f"  [green]✓[/]  {name}  [dim]{details}[/]")
            else:
                console.print(f"  [red]✗[/]  [bold]{name}[/]  {details}")

        console.print()
        if failed == 0:
            console.print("[bold green]✓ All checks passed — system is healthy[/bold green]")
        else:
            console.print(
                f"[bold red]✗ {failed} check(s) failed.[/bold red]  "
                "[dim]Run 'opencontext doctor' for details and recommendations.[/dim]"
            )
    except Exception as exc:
        console.print(f"[red]Doctor check failed: {exc}[/]")


def _run_verified_context() -> None:
    """Prompt for a task and render a verified-context result card."""
    _action_header("Verified context for a task")

    status = gather_kg_status(".")
    console.print(render_kg_header(status))
    console.print()
    if not status.indexed:
        console.print(
            "[yellow]No index found.[/] Choose [bold]Install / reconfigure[/] from the "
            "menu or run [bold]opencontext index .[/] first, then retry."
        )
        return

    query = prompts.text("Describe the task or question").strip()
    if not query:
        console.print("[dim]Cancelled — no task entered.[/]")
        return

    try:
        from pathlib import Path

        from opencontext_core.retrieval.contracts import VerifiedContextRequest
        from opencontext_core.runtime import OpenContextRuntime

        config_path = Path("opencontext.yaml")
        runtime = OpenContextRuntime(
            config_path=str(config_path) if config_path.exists() else None,
        )
        with console.status("[cyan]Building verified context...[/]", spinner="dots"):
            result = runtime.verify_context(VerifiedContextRequest(query=query))
    except Exception as exc:
        console.print(f"[red]Verified context failed: {exc}[/]")
        return

    console.print()
    console.print(render_verified_context(result, query=query))


def _run_backups() -> None:
    """Manage backups — opencontext config backup/restore/backups."""
    while True:
        _action_header("Backup Management")
        choice = prompts.select(
            "Backups",
            [
                ("create", "Create backup"),
                ("list", "List backups"),
                ("restore", "Restore backup"),
                ("cleanup", "Cleanup old backups"),
                ("back", "Back to main menu"),
            ],
            default="list",
        )

        if choice == "back":
            break

        action = {
            "create": _create_backup,
            "list": _list_backups,
            "restore": _restore_backup,
            "cleanup": _cleanup_backups,
        }.get(choice)
        if action is not None:
            action()

        prompts.pause("Press Enter to continue")


def _create_backup() -> None:
    """Create a config backup."""
    try:
        from opencontext_core.state import ConfigBackupManager

        backup_id = ConfigBackupManager.create_backup(description="manual")
        console.print(f"[green]✓ Backup created: {backup_id}[/]")
    except Exception as exc:
        console.print(f"[red]Backup failed: {exc}[/]")


def _list_backups() -> None:
    """List all config backups."""
    try:
        from opencontext_core.state import ConfigBackupManager

        backups = ConfigBackupManager.list_backups()
        if not backups:
            console.print("[yellow]No backups found.[/]")
            return
        console.print()
        for b in backups:
            console.print(f"  {b.id}  ({b.timestamp})  —  {b.description}")
        console.print(f"\n  {len(backups)} backup(s) available")
    except Exception as exc:
        console.print(f"[red]Failed to list backups: {exc}[/]")


def _restore_backup() -> None:
    """Restore from a backup."""
    try:
        from opencontext_core.state import ConfigBackupManager

        backups = ConfigBackupManager.list_backups()
        if not backups:
            console.print("[yellow]No backups to restore.[/]")
            return

        backup_id = prompts.select(
            "Select backup to restore",
            [(b.id, f"{b.id}  ({b.timestamp})  —  {b.description}") for b in backups],
            default=backups[0].id,
        )
        if ConfigBackupManager.restore_backup(backup_id):
            console.print(f"[green]✓ Restored from: {backup_id}[/]")
        else:
            console.print(f"[red]Backup not found: {backup_id}[/]")
    except Exception as exc:
        console.print(f"[red]Restore failed: {exc}[/]")


def _cleanup_backups() -> None:
    """Clean up old backups."""
    from opencontext_core import prompts
    from opencontext_core.state import ConfigBackupManager

    try:
        days = int(prompts.text("Keep backups newer than (days)", default="30"))
    except (TypeError, ValueError):
        days = 30
    removed, _ = ConfigBackupManager.cleanup(days)
    console.print(f"[green]✓ Removed {removed} backup(s) older than {days} days[/]")


def _run_uninstall() -> None:
    """Managed uninstall — removes project files AND global config."""
    _action_header("Uninstall OpenContext")

    if not prompts.confirm(
        "Remove all OpenContext configuration (project + global)?", default=False
    ):
        console.print("[yellow]Uninstall cancelled.[/]")
        return

    project_ok = False
    project_err = ""
    with console.status("[cyan]Removing project files...[/]", spinner="dots"):
        try:
            from opencontext_cli.main import _clean

            _clean(".", dry_run=False, force=True)
            project_ok = True
        except Exception as exc:
            project_err = str(exc)

    if not project_ok:
        console.print(f"[red]Project cleanup failed: {project_err}[/]")
        return

    console.print("[green]✓ Project files removed[/]")

    global_ok = False
    global_items: list[Any] = []
    with console.status("[cyan]Removing global installation state...[/]", spinner="dots"):
        try:
            from opencontext_core.configurator import KNOWN_AGENTS, Configurator

            # Surgically strip our managed block + MCP entry from each agent's
            # config — never unlink the whole CLAUDE.md / mcp.json, which would
            # wipe user-authored content and any other MCP server they configured.
            report = Configurator().deconfigure(list(KNOWN_AGENTS), scope="global")
            for result in report.get("results", []):
                global_items.extend(result.get("files", []))
            global_ok = True
        except Exception as exc:
            global_ok = False
            global_items = []
            console.print(f"[yellow]Global cleanup note: {exc}[/]")

    if global_ok:
        for item in global_items:
            console.print(f"  [dim]Removed: {item}[/]")
        console.print("[green]✓ Global installation state removed[/]")

    import shutil

    from opencontext_core.user_prefs import UserConfigStore

    # Canonical config dir (honors XDG_CONFIG_HOME / %APPDATA%), not a hardcode —
    # otherwise an XDG/Windows install leaves the real config dir behind.
    config_dir = UserConfigStore.CONFIG_DIR
    if config_dir.exists():
        shutil.rmtree(config_dir, ignore_errors=True)
        console.print(f"[green]✓ Config directory removed: {config_dir}[/]")

    console.print()
    console.print("[bold green]✓ OpenContext fully uninstalled[/bold green]")
