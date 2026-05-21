"""Sync CLI command — refresh managed assets after config changes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from opencontext_core.user_prefs import UserConfigStore

console = Console()


def add_sync_parser(subparsers: Any) -> None:
    """Add sync command parser."""

    sync_parser = subparsers.add_parser(
        "sync", help="Sync configuration and refresh managed assets."
    )
    sync_parser.add_argument(
        "--component",
        choices=["knowledge-graph", "mcp", "plugins", "all"],
        default="all",
        help="Component to sync (default: all).",
    )
    sync_parser.add_argument(
        "--agent",
        default="opencode",
        help="Agent to sync (default: opencode).",
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying.",
    )


def handle_sync(args: Any) -> None:
    """Handle sync command."""

    component = getattr(args, "component", "all")
    agent = getattr(args, "agent", "opencode")
    dry_run = getattr(args, "dry_run", False)

    store = UserConfigStore()
    prefs = store.load()

    console.print(Panel.fit("[bold]OpenContext Sync[/bold]", border_style="cyan"))

    checks: list[dict[str, Any]] = []

    if component in ("all", "knowledge-graph"):
        checks.append(_sync_kg(prefs, dry_run))

    if component in ("all", "mcp"):
        checks.append(_sync_mcp(prefs, agent, dry_run))

    if component in ("all", "plugins"):
        checks.append(_sync_plugins(prefs, dry_run))

    # Summary
    _show_sync_summary(checks)

    if dry_run:
        console.print("[yellow]── Dry run — no changes made ──[/]")
        return

    if not any(c["status"] == "applied" for c in checks):
        console.print("[green]✓ Everything is up to date.[/]")
    else:
        console.print("[green]✓ Sync complete.[/]")


def _sync_kg(prefs: Any, dry_run: bool) -> dict[str, Any]:
    """Sync knowledge graph config."""

    result = {"component": "knowledge-graph", "status": "ok", "message": ""}

    if not prefs.features.knowledge_graph:
        result["status"] = "skipped"
        result["message"] = "Knowledge Graph not enabled"
        return result

    # Check if MCP config references the right DB path
    expected_db = Path(".storage/opencontext/codegraph.db")
    if not expected_db.exists():
        result["status"] = "warning"
        result["message"] = f"Database not found: {expected_db}"
        return result

    result["message"] = "Knowledge Graph is active"
    return result


def _sync_mcp(prefs: Any, agent: str, dry_run: bool) -> dict[str, Any]:
    """Sync MCP configuration for the specified agent."""

    result = {"component": "mcp", "status": "ok", "message": ""}

    if not prefs.features.mcp_server:
        result["status"] = "skipped"
        result["message"] = "MCP Server not enabled"
        return result

    mcp_path = Path.home() / ".config" / agent / "mcp.json"
    if not mcp_path.parent.exists():
        result["status"] = "warning"
        result["message"] = f"Agent config dir not found: {mcp_path.parent}"
        return result

    if dry_run:
        result["status"] = "pending"
        result["message"] = f"Would update: {mcp_path}"
        return result

    # Write/update MCP config
    if agent == "opencode":
        try:
            from opencontext_cli.main import _setup_mcp_for_opencode

            _setup_mcp_for_opencode()
            result["status"] = "applied"
            result["message"] = f"MCP config updated: {mcp_path}"
        except ImportError:
            result["status"] = "warning"
            result["message"] = "MCP setup not available"
    else:
        result["status"] = "skipped"
        result["message"] = f"MCP sync not yet supported for: {agent}"

    return result


def _sync_plugins(prefs: Any, dry_run: bool) -> dict[str, Any]:
    """Sync plugin state."""

    result = {"component": "plugins", "status": "ok", "message": ""}

    from opencontext_core.plugin_system import PluginRegistry

    registry = PluginRegistry()
    plugins = registry.discover()

    if not plugins:
        result["status"] = "skipped"
        result["message"] = "No plugins installed"
        return result

    enabled = [p.name for p in plugins if p.enabled]
    disabled = [p.name for p in plugins if not p.enabled]

    if enabled:
        result["message"] = f"Enabled: {', '.join(enabled)}"
    if disabled:
        result["message"] += f" | Disabled: {', '.join(disabled)}"

    return result


def _show_sync_summary(checks: list[dict[str, Any]]) -> None:
    """Display sync results."""

    table = Table(title="Sync Results", box=None)
    table.add_column("Component")
    table.add_column("Status")
    table.add_column("Message")

    status_styles = {
        "ok": "green",
        "applied": "cyan",
        "warning": "yellow",
        "skipped": "white",
        "pending": "dim",
    }

    for check in checks:
        style = status_styles.get(check["status"], "white")
        table.add_row(
            check["component"],
            f"[{style}]{check['status']}[/]",
            check["message"],
        )

    console.print(table)
