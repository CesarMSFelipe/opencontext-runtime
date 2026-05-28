"""Main TUI menu for OpenContext.

Run opencontext with no arguments to launch this interactive menu.
"""

from __future__ import annotations

import sys

from rich.panel import Panel
from rich.prompt import Prompt

from opencontext_cli.commands.update_cmd import handle_upgrade
from opencontext_core.dx.console_styles import console

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

    for line in (LOGO if use_full else COMPACT_LOGO):
        console.print(line)


def run_main_menu() -> None:
    """Show the main OpenContext menu and delegate to the selected command."""

    while True:
        try:
            console.clear()
        except Exception:
            pass

        _show_logo()
        console.print()
        console.print(
            Panel(
                "\n".join([
                    "[dim]── Setup & Maintenance ──────────────────[/]",
                    "  [bold #00C9A7]1[/]  Start installation",
                    "  [bold #00C9A7]2[/]  Upgrade tools",
                    "  [bold #00C9A7]3[/]  Sync configs",
                    "  [bold #00C9A7]4[/]  Upgrade + Sync",
                    "",
                    "[dim]── Development ────────────────────────────[/]",
                    "  [bold #00A8E8]5[/]  Configure models",
                    "  [bold #00A8E8]6[/]  Create Agent integration",
                    "  [bold #00A8E8]7[/]  Community plugins",
                    "  [bold #00A8E8]8[/]  SDD profiles",
                    "  [bold #00A8E8]11[/] Context memory",
                    "",
                    "[dim]── Management ─────────────────────────────[/]",
                    "  [bold #845EC2]9[/]  Manage backups",
                    "  [bold #845EC2]10[/] Uninstall",
                    "",
                    "  [dim]q[/]   Quit",
                    "",
                    "[dim]Enter a number or q[/]",
                ]),
                border_style="#00C9A7",
                padding=(1, 2),
            )
        )
        console.print()

        choice = Prompt.ask(
            "Select option",
            choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "q"],
            default="q",
        )

        if choice == "1":
            _run_install()
        elif choice == "2":
            _run_upgrade()
        elif choice == "3":
            _run_sync()
        elif choice == "4":
            _run_upgrade_sync()
        elif choice == "5":
            _run_configure_models()
        elif choice == "6":
            _run_create_agent()
        elif choice == "7":
            _run_plugins()
        elif choice == "8":
            _run_sdd_profiles()
        elif choice == "11":
            _run_memory_tools()
        elif choice == "9":
            _run_backups()
        elif choice == "10":
            _run_uninstall()
        elif choice == "q":
            console.print("[dim]Goodbye.[/]")
            break

        console.print("\n[dim]Press Enter to return to menu...[/]")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            break


# ── Menu action dispatchers ─────────────────────────────────────────────


def _run_install() -> None:
    """Start installation — opencontext install."""
    console.print("\n[bold]Starting installation...[/]")
    try:
        from opencontext_cli.main import _install

        class _InstallArgs:
            root: str = "."
            yes: bool = False

        _install(_InstallArgs())
    except Exception as exc:
        console.print(f"[red]Installation failed: {exc}[/]")


def _run_upgrade() -> None:
    """Upgrade tools — opencontext upgrade."""
    console.print("\n[bold]Checking for updates...[/]")
    handle_upgrade(
        type(
            "Args",
            (),
            {},
        )()
    )


def _run_sync() -> None:
    """Sync configs — opencontext sync."""
    console.print("\n[bold]Syncing configs...[/]")
    try:
        from opencontext_cli.commands.sync_cmd import handle_sync

        handle_sync(type("Args", (), {"sync_command": None})())
        console.print("[green]✓ Configs synced[/]")
    except Exception as exc:
        console.print(f"[red]Sync failed: {exc}[/]")


def _run_upgrade_sync() -> None:
    """Upgrade tools and sync configs."""
    _run_upgrade()
    console.print()
    _run_sync()


def _run_configure_models() -> None:
    """Configure models — opencontext config wizard."""
    console.print("\n[bold]Model configuration[/]")
    try:
        from opencontext_core.wizard import run_wizard_menu

        run_wizard_menu()
        return  # wizard has its own loop
    except Exception:
        pass

    # Fallback: simple prompts
    from opencontext_core.user_prefs import UserConfigStore

    store = UserConfigStore()
    prefs = store.load()

    from rich.prompt import Prompt as RPrompt

    console.print("\n[bold]Current model configuration:[/]")
    console.print(f"  Default provider: {prefs.default_provider}")
    console.print(f"  Default model:    {prefs.default_model}")
    console.print()

    provider = RPrompt.ask("Default provider", default=prefs.default_provider or "mock")
    model = RPrompt.ask("Default model", default=prefs.default_model or "mock-llm")
    prefs.default_provider = provider
    prefs.default_model = model
    store.save(prefs)
    console.print("[green]✓ Model configuration saved[/]")


def _run_create_agent() -> None:
    """Create your own Agent — opencontext agent init."""
    console.print("\n[bold]Creating agent integration...[/]")
    try:
        from opencontext_cli.main import _agent

        _agent(
            type(
                "Args",
                (),
                {
                    "agent_command": "init",
                    "target": "generic",
                    "root": ".",
                    "force": False,
                },
            )
        )
        console.print("[green]✓ Agent integration created[/]")
    except Exception as exc:
        console.print(f"[red]Agent creation failed: {exc}[/]")


def _run_plugins() -> None:
    """Browse plugins — opencontext plugin."""
    console.print("\n[bold]OpenCode Community Plugins[/]")
    try:
        from opencontext_cli.commands.plugin_cmd import handle_plugin

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
    """Configure SDD profiles — opencontext config wizard."""
    console.print("\n[bold]OpenCode SDD Profiles[/]")
    try:
        from opencontext_core.user_prefs import UserConfigStore

        store = UserConfigStore()
        prefs = store.load()
        from rich.prompt import Prompt as RPrompt

        console.print(f"  Current SDD profile: {prefs.sdd.sdd_model_profile}")
        console.print(f"  Current TDD mode:    {prefs.sdd.tdd_mode}")
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
        console.print("[green]✓ SDD profiles updated[/]")
    except Exception as exc:
        console.print(f"[red]Failed: {exc}[/]")


def _run_backups() -> None:
    """Manage backups — opencontext config backup/restore/backups."""
    console.print("\n[bold]Backup Management[/]")

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


def _run_memory_tools() -> None:
    """Context memory — opencontext memory list."""
    console.print("\n[bold]Context Memory[/]")
    try:
        from opencontext_cli.main import _memory

        class _MemoryArgs:
            memory_command: str = "list"
            config: str = "opencontext.yaml"

        _memory(_MemoryArgs())
    except Exception as exc:
        console.print(f"[red]Memory list failed: {exc}[/]")


def _run_uninstall() -> None:
    """Managed uninstall — removes project files AND global config."""
    console.print("\n[bold]Uninstall OpenContext[/]")
    from rich.prompt import Confirm

    if not Confirm.ask("Remove all OpenContext configuration (project + global)?", default=False):
        console.print("[yellow]Uninstall cancelled.[/]")
        return

    # Step 1: project-local files
    try:
        from opencontext_cli.main import _clean

        _clean(".", dry_run=False, force=True)
        console.print("[green]✓ Project files removed[/]")
    except Exception as exc:
        console.print(f"[red]Project cleanup failed: {exc}[/]")
        return

    # Step 2: global install state
    try:
        from opencontext_core.install_manager import InstallationManager

        result = InstallationManager().uninstall(keep_backups=False, yes=True)
        if result.get("removed"):
            for item in result["removed"]:
                console.print(f"  Removed: [dim]{item}[/]")
        console.print("[green]✓ Global installation state removed[/]")
    except Exception as exc:
        console.print(f"[yellow]Global cleanup note: {exc}[/]")

    # Step 3: global user config directory
    import shutil
    from pathlib import Path

    config_dir = Path.home() / ".config" / "opencontext"
    if config_dir.exists():
        shutil.rmtree(config_dir, ignore_errors=True)
        console.print(f"[green]✓ Config directory removed: {config_dir}[/]")

    console.print()
    console.print("[bold green]✓ OpenContext fully uninstalled[/]")
