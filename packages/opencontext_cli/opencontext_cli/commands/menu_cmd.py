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
    from opencontext_core.i18n import load_language_from_config

    load_language_from_config(".")  # open the menu in the project's configured language

    # NOTE: CockpitScreen is the default bare-opencontext entry point.
    # Falls back to HomeScreen, then to the text-only message.
    try:
        from opencontext_cli.tui import run_cockpit_tui

        if run_cockpit_tui():
            return
    except Exception:
        pass

    try:
        from opencontext_cli.tui import run_home_tui

        if run_home_tui():
            return
    except Exception:
        pass

    # No terminal (or the TUI could not start) → no interactive menu exists. Point
    # the user at the CLI rather than a second, parallel selector.
    console.print(
        "[yellow]The interactive menu needs a terminal.[/] "
        "Run a subcommand instead, e.g. [cyan]opencontext --help[/], "
        "[cyan]opencontext install[/], or [cyan]opencontext doctor[/]."
    )


def run_config_menu() -> None:
    """Open the unified configuration surface — the one Textual TUI.

    There is a single menu system (``opencontext`` home and ``opencontext config``
    both open it). Without a terminal there is no interactive menu at all, so point
    the user at the non-interactive equivalents rather than spawning a second,
    parallel selector — duplicate menus are exactly what this unification removes.
    """
    from opencontext_core.i18n import load_language_from_config

    load_language_from_config(".")  # open the menu in the project's configured language

    try:
        from opencontext_cli.tui import run_config_tui

        if run_config_tui():
            return
    except Exception:
        pass

    console.print(
        "[yellow]The configuration menu needs a terminal.[/] Configure non-interactively with a "
        "direct subcommand: [cyan]config reconfigure <section>[/] · [cyan]config set[/] · "
        "[cyan]config get[/] (or [cyan]opencontext init --non-interactive[/] for first-time setup)."
    )


def _run_install() -> None:
    """Start installation — opencontext install."""
    _action_header("Install / Reconfigure")
    try:
        from opencontext_cli.main import _install

        _install(argparse.Namespace(root=".", yes=False))
    except Exception as exc:
        console.error(f"Installation failed: {exc}")


def _run_upgrade() -> None:
    """Upgrade all packages and re-sync the environment."""
    _action_header("Upgrade all packages")
    handle_upgrade(type("Args", (), {})())
    console.print()
    console.dim("Re-syncing environment after upgrade...")
    try:
        from opencontext_cli.commands.sync_cmd import handle_sync

        handle_sync(type("Args", (), {"sync_command": None})())
    except Exception as exc:
        console.warning(f"Re-sync note: {exc}")


def _run_sync() -> None:
    """Re-sync environment — refresh configs, MCP, and plugin state."""
    _action_header("Re-sync environment")
    try:
        from opencontext_cli.commands.sync_cmd import handle_sync

        handle_sync(type("Args", (), {"sync_command": None})())
    except Exception as exc:
        console.error(f"Sync failed: {exc}")


def _offer_engram_install() -> None:
    """Provision Engram (PyPI) when a backend needs it but it's not installed."""
    try:
        from opencontext_core.memory.engram_bridge import detect_engram
    except Exception:
        return
    if detect_engram():
        return

    console.print()
    console.print(
        "[yellow]Engram isn't installed.[/] It's a standalone package — no gentle-ai required."
    )
    if not prompts.confirm("Install Engram now?", default=True):
        console.print(
            "[dim]Skipped — this backend falls back to the local engine until Engram is present.[/]"
        )
        console.print(
            "[dim]Install later:[/] [cyan]pipx install engram[/] [dim](or pip install engram)[/]"
        )
        return

    import shutil
    import subprocess

    # Prefer pipx so the `engram` CLI lands on PATH (detect_engram looks for it);
    # fall back to pip in the current interpreter.
    cmd = (
        ["pipx", "install", "engram"]
        if shutil.which("pipx")
        else [sys.executable, "-m", "pip", "install", "engram"]
    )
    console.print(f"[dim]$ {' '.join(cmd)}[/]")
    try:
        with console.status("Installing Engram..."):
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        console.print("[red]Install timed out.[/] Try [cyan]pipx install engram[/] manually.")
        return
    except Exception as exc:
        console.print(f"[red]Install error:[/] {exc}")
        return

    if res.returncode == 0 and detect_engram():
        console.success("Engram installed and detected.")
    elif res.returncode == 0:
        console.print(
            "[yellow]Installed, but the 'engram' CLI isn't on PATH yet.[/] "
            "Open a new shell (or run [cyan]pipx ensurepath[/]) and retry."
        )
    else:
        console.print(f"[red]Install failed.[/] {(res.stderr or '').strip()[:200]}")
        console.print("[dim]Try manually:[/] [cyan]pipx install engram[/]")


def _run_memory_tools() -> None:
    """Context memory — list and search memory entries."""
    _action_header("Context memory")
    try:
        from opencontext_cli.main import _memory

        _memory(argparse.Namespace(memory_command="list", config="opencontext.yaml"))
    except Exception as exc:
        console.error(f"Memory list failed: {exc}")


def _run_doctor() -> None:
    """Run health checks — opencontext doctor."""
    _action_header("Doctor — Health Check")
    try:
        from pathlib import Path

        from opencontext_core.doctor.checks import run_doctor
        from opencontext_core.runtime import OpenContextRuntime

        with console.status("Running health checks..."):
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
        console.error(f"Doctor check failed: {exc}")


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
        with console.status("Building verified context..."):
            result = runtime.verify_context(VerifiedContextRequest(query=query))
    except Exception as exc:
        console.error(f"Verified context failed: {exc}")
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
        console.success(f"Backup created: {backup_id}")
    except Exception as exc:
        console.error(f"Backup failed: {exc}")


def _list_backups() -> None:
    """List all config backups."""
    try:
        from opencontext_core.state import ConfigBackupManager

        backups = ConfigBackupManager.list_backups()
        if not backups:
            console.info("No backups yet.")
            return
        console.print()
        for b in backups:
            console.print(f"  {b.id}  ({b.timestamp})  —  {b.description}")
        console.print(f"\n  {len(backups)} backup(s) available")
    except Exception as exc:
        console.error(f"Failed to list backups: {exc}")


def _restore_backup() -> None:
    """Restore from a backup."""
    try:
        from opencontext_core.state import ConfigBackupManager

        backups = ConfigBackupManager.list_backups()
        if not backups:
            console.info("No backups to restore yet.")
            return

        backup_id = prompts.select(
            "Select backup to restore",
            [(b.id, f"{b.id}  ({b.timestamp})  —  {b.description}") for b in backups],
            default=backups[0].id,
        )
        if ConfigBackupManager.restore_backup(backup_id):
            console.success(f"Restored from: {backup_id}")
        else:
            console.error(f"Backup not found: {backup_id}")
    except Exception as exc:
        console.error(f"Restore failed: {exc}")


def _cleanup_backups() -> None:
    """Clean up old backups."""
    from opencontext_core import prompts
    from opencontext_core.state import ConfigBackupManager

    try:
        days = int(prompts.text("Keep backups newer than (days)", default="30"))
    except (TypeError, ValueError):
        days = 30
    removed, _ = ConfigBackupManager.cleanup(days)
    console.success(f"Removed {removed} backup(s) older than {days} days")


def _run_uninstall() -> None:
    """Managed uninstall — removes project files AND global config."""
    _action_header("Uninstall OpenContext")

    if not prompts.confirm(
        "Remove all OpenContext configuration (project + global)?", default=False
    ):
        console.warning("Uninstall cancelled.")
        return

    project_ok = False
    project_err = ""
    with console.status("Removing project files..."):
        try:
            from opencontext_cli.main import _clean

            _clean(".", dry_run=False, force=True)
            project_ok = True
        except Exception as exc:
            project_err = str(exc)

    if not project_ok:
        console.error(f"Project cleanup failed: {project_err}")
        return

    console.success("Project files removed")

    global_ok = False
    global_items: list[Any] = []
    with console.status("Removing global installation state..."):
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
            console.warning(f"Global cleanup note: {exc}")

    if global_ok:
        for item in global_items:
            console.dim(f"  Removed: {item}")
        console.success("Global installation state removed")

    import shutil

    from opencontext_core.user_prefs import UserConfigStore

    # Canonical config dir (honors XDG_CONFIG_HOME / %APPDATA%), not a hardcode —
    # otherwise an XDG/Windows install leaves the real config dir behind.
    config_dir = UserConfigStore.CONFIG_DIR
    if config_dir.exists():
        shutil.rmtree(config_dir, ignore_errors=True)
        console.success(f"Config directory removed: {config_dir}")

    console.print()
    console.success("OpenContext fully uninstalled")
