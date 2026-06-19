"""Main TUI menu for OpenContext.

Run opencontext with no arguments to launch this interactive menu.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from opencontext_cli.commands.update_cmd import handle_upgrade
from opencontext_cli.commands.verified_context_view import (
    gather_kg_status,
    render_kg_header,
    render_verified_context,
)
from opencontext_core.dx.console_styles import console
from opencontext_core.update import EcosystemUpdateChecker, UpdateChecker

# ── Console logo — knowledge graph motif, brand colors ──────────────────
#
# Visual layout (terminal rendering, markup stripped):
#
#   ◉──◉──◉    OpenContext Runtime           node cols: left=2 mid=5 right=8
#   │     │    Context Engineering...         ── edges are 2 chars each
#   ◉──◉  ◉
#   │  │       * 87% token reduction  * SDD   both bottom nodes are connected
#   ◉──◉       * MCP server  * 13+ agents     up via │ at cols 2 and 5
#
# Graph edges:  A──B──C / │     │ / D──E  F / │  │ / G──H
# (F is a leaf — only connected upward to C)

LOGO = [
    "",
    "  [bold #00C9A7]◉[/][dim]──[/][bold #00A8E8]◉[/][dim]──[/][bold #845EC2]◉[/]    [bold white]OpenContext Runtime[/]",  # noqa: E501
    "  [#00C9A7]│[/]     [#845EC2]│[/]    [dim]Context Engineering for AI Agents[/]",
    "  [#00C9A7]◉[/][dim]──[/][#00A8E8]◉[/]  [#845EC2]◉[/]",
    "  [#00C9A7]│[/]  [#00A8E8]│[/]       [bold #00C9A7]*[/] [bold]87% token reduction[/]  [#00A8E8]*[/] SDD workflow",  # noqa: E501
    "  [#00C9A7]◉[/][dim]──[/][#00A8E8]◉[/]       [#845EC2]*[/] MCP server  [#00C9A7]*[/] 13+ agents  [#00A8E8]*[/] Zero secrets",  # noqa: E501
    "",
]

COMPACT_LOGO = [
    "  [bold #00C9A7]◉──◉[/]  [bold white]OpenContext Runtime[/]",
    "  [#00C9A7]│  │[/]  [dim]Context Engineering · 87% token reduction[/]",
    "  [#00C9A7]◉──◉[/]  [dim]SDD · MCP · 13+ agents · Zero secrets[/]",
]


def _show_logo() -> None:
    """Print the OpenContext logo, falling back to compact if terminal is small."""
    try:
        width = __import__("shutil").get_terminal_size().columns
        height = __import__("shutil").get_terminal_size().lines
        use_full = width >= 64 and height >= len(LOGO) + 14
    except Exception:
        use_full = False

    for line in LOGO if use_full else COMPACT_LOGO:
        console.print(line)


def _action_header(title: str) -> None:
    """Clear terminal and show a consistent action screen header."""
    try:
        console.clear()
    except Exception:
        pass
    console.print(f"\n  [bold white]OpenContext[/bold white]   [dim]>[/dim]   [bold]{title}[/bold]")
    console.print()


def run_main_menu() -> None:
    """Show the main OpenContext menu and delegate to the selected command."""

    while True:
        try:
            console.clear()
        except Exception:
            pass

        _show_logo()
        console.print()
        _print_kg_header()
        console.print()

        grid = Table.grid(expand=True, padding=(0, 1))
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)

        grid.add_row(
            Panel(
                "\n".join(
                    [
                        " [bold #00C9A7]1[/]  Install / reconfigure",
                        " [bold #00C9A7]2[/]  Upgrade all packages",
                        " [bold #00C9A7]3[/]  Re-sync environment",
                    ]
                ),
                title="[dim]Setup[/]",
                border_style="#00C9A7",
                padding=(0, 1),
            ),
            Panel(
                "\n".join(
                    [
                        " [bold #00A8E8]4[/]  Providers & models",
                        " [bold #00A8E8]5[/]  Agent integrations",
                        " [bold #00A8E8]6[/]  Plugins",
                        " [bold #00A8E8]7[/]  SDD & TDD settings",
                        " [bold #00A8E8]8[/]  Context memory",
                    ]
                ),
                title="[dim]Configure[/]",
                border_style="#00A8E8",
                padding=(0, 1),
            ),
            Panel(
                "\n".join(
                    [
                        " [bold #00C9A7]12[/]  [bold]Verified context for a task[/]",
                        " [bold #845EC2] 9[/]  Doctor",
                        " [bold #845EC2]10[/]  Backups",
                        " [bold #845EC2]11[/]  Uninstall",
                        "",
                        "  [dim]q[/]   Quit",
                    ]
                ),
                title="[dim]Tools[/]",
                border_style="#845EC2",
                padding=(0, 1),
            ),
        )

        console.print(grid)
        console.print()
        _print_update_banner()
        console.print("[dim]  Enter a number or q[/]")
        console.print()

        choice = Prompt.ask(
            "Select option",
            choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "q"],
            default="q",
        )

        if choice == "1":
            _run_install()
        elif choice == "2":
            _run_upgrade()
        elif choice == "3":
            _run_sync()
        elif choice == "4":
            _run_configure_models()
        elif choice == "5":
            _run_agent_integrations()
        elif choice == "6":
            _run_plugins()
        elif choice == "7":
            _run_sdd_profiles()
        elif choice == "8":
            _run_memory_tools()
        elif choice == "9":
            _run_doctor()
        elif choice == "10":
            _run_backups()
        elif choice == "11":
            _run_uninstall()
        elif choice == "12":
            _run_verified_context()
        elif choice == "q":
            console.print("[dim]Goodbye.[/]")
            break

        console.print("\n[dim]Press Enter to return to menu...[/]")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            break


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
            f"  [bold yellow]Updates available:[/] {joined}  [dim](option 2 to upgrade)[/]"
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

        class _InstallArgs:
            root: str = "."
            yes: bool = False

        import argparse

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
    """Configure providers and models — opencontext config wizard."""
    _action_header("Providers & models")
    try:
        from opencontext_core.wizard import run_wizard_menu

        run_wizard_menu()
        return
    except Exception:
        pass

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

    try:
        from InquirerPy import inquirer
        from InquirerPy.base.control import Choice

        provider = inquirer.select(
            message="Default provider",
            choices=[Choice(value=p, name=p) for p in known_providers],
            default=prefs.default_provider or "anthropic",
        ).execute()

        model_choices = known_models.get(provider, [])
        if model_choices:
            model = inquirer.select(
                message="Default model",
                choices=[Choice(value=m, name=m) for m in model_choices],
                default=prefs.default_model
                if prefs.default_model in model_choices
                else model_choices[0],
            ).execute()
        else:
            model = inquirer.text(
                message="Default model",
                default=prefs.default_model or "",
            ).execute()
    except ImportError:
        from rich.prompt import Prompt as RPrompt

        default_prov = prefs.default_provider or "anthropic"
        provider = RPrompt.ask("Default provider", choices=known_providers, default=default_prov)
        model = RPrompt.ask("Default model", default=prefs.default_model or "")

    prefs.default_provider = provider
    prefs.default_model = model
    store.save(prefs)
    console.print("[green]✓ Model configuration saved[/]")


def _run_agent_integrations() -> None:
    """Configure agent integrations — show current state, offer regeneration."""
    _action_header("Agent integrations")

    from opencontext_core.adapters.agent_manifest import AgentIntegrationGenerator, AgentTarget
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

    supported = [t.value for t in AgentTarget]
    console.print()

    try:
        from InquirerPy import inquirer
        from InquirerPy.base.control import Choice

        target = inquirer.select(
            message="Regenerate integration files for which agent?",
            choices=[Choice(value=v, name=v) for v in supported],
            default="opencode",
        ).execute()
    except ImportError:
        from rich.prompt import Prompt as RPrompt

        console.print(f"[bold]Available agents:[/] {', '.join(supported)}")
        target = RPrompt.ask(
            "Regenerate integration files for which agent?",
            choices=supported,
            default="opencode",
        ).strip()

    if not target:
        return

    try:
        from pathlib import Path

        generator = AgentIntegrationGenerator()
        files = generator.generate(Path("."), target=AgentTarget(target), force=True)
        console.print(f"[green]✓ Generated {len(files)} file(s) for {target}[/]")
        for f in files:
            console.print(f"  [dim]{f}[/]")

        prefs.agent_integrations[target] = True
        store.save(prefs)
    except ValueError:
        console.print(f"[red]Unknown agent target: {target}[/]")
        console.print(f"  Supported: {', '.join(supported)}")
    except Exception as exc:
        console.print(f"[red]Failed: {exc}[/]")


def _run_plugins() -> None:
    """Browse and manage plugins."""
    _action_header("Plugins")
    try:
        from opencontext_core.plugin_system import PluginRegistry

        registry = PluginRegistry()
        installed = registry.discover()
        if installed:
            console.print(f"[bold]Installed plugins ({len(installed)}):[/]")
            for p in installed:
                enabled = "[green]●[/]" if p.enabled else "[dim]○[/]"
                console.print(
                    f"  {enabled}  [bold]{p.name}[/] v{p.version}  [dim]{p.description}[/]"
                )
            console.print()
        else:
            console.print("[dim]No plugins installed.[/]\n")

        from opencontext_cli.commands.plugin_cmd import handle_plugin

        with console.status("[cyan]Fetching plugin registry...[/]", spinner="dots"):
            handle_plugin(
                type(
                    "Args",
                    (),
                    {
                        "plugin_command": "search",
                        "registry": None,
                        "query": "",
                        "refresh": False,
                        "json": False,
                    },
                )
            )
    except Exception as exc:
        console.print(f"[red]Plugin search failed: {exc}[/]")


def _run_sdd_profiles() -> None:
    """Configure SDD model profile and TDD mode."""
    _action_header("SDD & TDD settings")
    try:
        from opencontext_core.user_prefs import UserConfigStore

        store = UserConfigStore()
        prefs = store.load()
        from rich.prompt import Prompt as RPrompt

        console.print("[bold]Current settings:[/]")
        console.print(f"  SDD model profile: [cyan]{prefs.sdd.sdd_model_profile or 'default'}[/]")
        console.print(f"  TDD mode:          [cyan]{prefs.sdd.tdd_mode or 'ask'}[/]")
        console.print(f"  Token budget/phase: [cyan]{getattr(prefs, 'sdd_token_budget', 3000)}[/]")
        console.print()

        profile = RPrompt.ask(
            "SDD model profile",
            choices=["default", "cheap", "hybrid", "premium"],
            default=prefs.sdd.sdd_model_profile or "hybrid",
        )
        tdd = RPrompt.ask(
            "TDD mode",
            choices=["ask", "strict", "off"],
            default=prefs.sdd.tdd_mode or "ask",
        )
        prefs.sdd.sdd_model_profile = profile
        prefs.sdd.tdd_mode = tdd
        store.save(prefs)
        console.print()
        console.print("[green]✓ SDD & TDD settings saved[/]")
    except Exception as exc:
        console.print(f"[red]Failed: {exc}[/]")


def _run_memory_tools() -> None:
    """Context memory — list and search memory entries."""
    _action_header("Context memory")
    try:
        from opencontext_cli.main import _memory

        class _MemoryArgs:
            memory_command: str = "list"
            config: str = "opencontext.yaml"

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
            "[yellow]No index found.[/] Run [bold]option 1[/] (Install) or "
            "[bold]opencontext index .[/] first, then retry."
        )
        return

    from rich.prompt import Prompt as RPrompt

    query = RPrompt.ask("Describe the task or question").strip()
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
        try:
            console.clear()
        except Exception:
            pass
        console.print(
            Panel(
                "\n".join(
                    [
                        "[bold]Backup Management[/]",
                        "",
                        "  [cyan]1[/]  Create backup",
                        "  [cyan]2[/]  List backups",
                        "  [cyan]3[/]  Restore backup",
                        "  [cyan]4[/]  Cleanup old backups",
                        "  [cyan]b[/]  Back to main menu",
                        "  [cyan]q[/]  Quit",
                    ]
                ),
                border_style="yellow",
                padding=(1, 2),
            )
        )
        console.print()
        choice = Prompt.ask(
            "Select option",
            choices=["1", "2", "3", "4", "b", "q"],
            default="b",
        )

        if choice == "1":
            _create_backup()
        elif choice == "2":
            _list_backups()
        elif choice == "3":
            _restore_backup()
        elif choice == "4":
            _cleanup_backups()
        elif choice == "b":
            break
        elif choice == "q":
            console.print("[dim]Goodbye.[/]")
            sys.exit(0)

        console.print("\n[dim]Press Enter to continue...[/]")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            break


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

        from rich.prompt import Prompt as RPrompt

        console.print("\n[bold]Available backups:[/]")
        for i, b in enumerate(backups, 1):
            console.print(f"  {i}. {b.id}  ({b.timestamp})")
        idx = RPrompt.ask(
            "Select backup to restore",
            choices=[str(i) for i in range(1, len(backups) + 1)],
        )
        backup_id = backups[int(idx) - 1].id
        if ConfigBackupManager.restore_backup(backup_id):
            console.print(f"[green]✓ Restored from: {backup_id}[/]")
        else:
            console.print(f"[red]Backup not found: {backup_id}[/]")
    except Exception as exc:
        console.print(f"[red]Restore failed: {exc}[/]")


def _cleanup_backups() -> None:
    """Clean up old backups."""
    import shutil
    from datetime import datetime, timedelta

    from rich.prompt import IntPrompt

    from opencontext_core.state import ConfigBackupManager

    days = IntPrompt.ask("Keep backups newer than (days)", default=30)
    backups = ConfigBackupManager.list_backups()
    cutoff = datetime.now() - timedelta(days=days)
    removed = 0
    for b in backups:
        try:
            ts = datetime.strptime(b.timestamp, "%Y%m%dT%H%M%S")
            if ts < cutoff:
                backup_dir = ConfigBackupManager.BACKUP_DIR / b.id
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                removed += 1
        except (ValueError, OSError):
            continue
    console.print(f"[green]✓ Removed {removed} backup(s) older than {days} days[/]")


def _run_uninstall() -> None:
    """Managed uninstall — removes project files AND global config."""
    _action_header("Uninstall OpenContext")

    if not Confirm.ask("Remove all OpenContext configuration (project + global)?", default=False):
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
            from opencontext_core.install_manager import InstallationManager

            result = InstallationManager().uninstall(keep_backups=False, yes=True)
            global_items = result.get("removed", [])
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
    from pathlib import Path

    config_dir = Path.home() / ".config" / "opencontext"
    if config_dir.exists():
        shutil.rmtree(config_dir, ignore_errors=True)
        console.print(f"[green]✓ Config directory removed: {config_dir}[/]")

    console.print()
    console.print("[bold green]✓ OpenContext fully uninstalled[/bold green]")
