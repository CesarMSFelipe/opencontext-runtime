"""Sync CLI command — refresh managed assets after config changes."""

from __future__ import annotations

import re
import subprocess
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
    sync_sub = sync_parser.add_subparsers(dest="sync_command")

    # sync issues
    issues_parser = sync_sub.add_parser(
        "issues",
        help="Create/update GitHub Issues from a change's tasks.md file.",
    )
    issues_parser.add_argument(
        "--change",
        default=None,
        help="SDD change name (reads openspec/changes/<change>/tasks.md).",
    )
    issues_parser.add_argument(
        "--tasks-file",
        default=None,
        help="Explicit path to a tasks.md file.",
    )
    issues_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview issues without creating them.",
    )
    issues_parser.add_argument(
        "--repo",
        default=None,
        help="GitHub repo (owner/name). Auto-detected from git remote if omitted.",
    )

    # sync config (default behavior, preserved as a subcommand)
    config_parser = sync_sub.add_parser(
        "config",
        help="Sync configuration and refresh managed assets.",
    )
    config_parser.add_argument(
        "--component",
        choices=["knowledge-graph", "mcp", "plugins", "all"],
        default="all",
        help="Component to sync (default: all).",
    )
    config_parser.add_argument("--agent", default="opencode")
    config_parser.add_argument("--dry-run", action="store_true")

    # Keep flat flags on sync itself for backward compat
    sync_parser.add_argument(
        "--component",
        choices=["knowledge-graph", "mcp", "plugins", "all"],
        default="all",
    )
    sync_parser.add_argument("--agent", default="opencode")
    sync_parser.add_argument("--dry-run", action="store_true")


def handle_sync(args: Any) -> None:
    """Handle sync command."""

    sync_cmd = getattr(args, "sync_command", None)

    if sync_cmd == "issues":
        _handle_sync_issues(args)
        return

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

    _show_sync_summary(checks)

    if dry_run:
        console.print("[yellow]── Dry run — no changes made ──[/]")
        return

    if not any(c["status"] == "applied" for c in checks):
        console.print("[green]✓ Everything is up to date.[/]")
    else:
        console.print("[green]✓ Sync complete.[/]")


# ── sync issues ───────────────────────────────────────────────────────────────


def parse_tasks_from_md(path: Path) -> list[dict[str, str]]:
    """Parse task items from a tasks.md file.

    Reads lines matching '- [ ] ...' (open) and '- [x] ...' (closed).
    Returns a list of dicts with 'title' and 'state' keys.
    """
    tasks: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if re.match(r"^- \[ \] ", stripped):
            tasks.append({"title": stripped[6:].strip(), "state": "open"})
        elif re.match(r"^- \[x\] ", stripped, re.IGNORECASE):
            tasks.append({"title": stripped[6:].strip(), "state": "closed"})
    return tasks


def _resolve_tasks_file(args: Any) -> Path | None:
    """Resolve tasks.md path from --change or --tasks-file args."""
    if getattr(args, "tasks_file", None):
        return Path(args.tasks_file)
    change = getattr(args, "change", None)
    if change:
        return Path("openspec") / "changes" / change / "tasks.md"
    return None


def _handle_sync_issues(args: Any) -> None:
    """Handle sync issues subcommand."""
    tasks_file = _resolve_tasks_file(args)
    dry_run = getattr(args, "dry_run", False)
    repo = getattr(args, "repo", None)

    if tasks_file is None:
        console.print("[red]Error: specify --change <name> or --tasks-file <path>[/]")
        return

    if not tasks_file.exists():
        console.print(f"[red]Tasks file not found: {tasks_file}[/]")
        return

    tasks = parse_tasks_from_md(tasks_file)
    if not tasks:
        console.print("[yellow]No task items found in tasks file.[/]")
        return

    console.print(f"Found [bold]{len(tasks)}[/] task(s) in {tasks_file}")

    if dry_run:
        console.print("[yellow]── Dry run — issues NOT created ──[/]")
        for t in tasks:
            icon = "○" if t["state"] == "open" else "✓"
            console.print(f"  {icon} {t['title']}")
        return

    created = 0
    skipped = 0
    for task in tasks:
        if task["state"] == "closed":
            skipped += 1
            continue
        cmd = ["gh", "issue", "create", "--title", task["title"]]
        if repo:
            cmd += ["--repo", repo]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            created += 1
            console.print(f"  [green]✓[/] {task['title']}")
        else:
            console.print(f"  [red]✗[/] {task['title']}: {result.stderr.strip()}")

    console.print(f"[green]Created {created} issue(s)[/], skipped {skipped} closed task(s).")


# ── sync config helpers ───────────────────────────────────────────────────────


def _sync_kg(prefs: Any, dry_run: bool) -> dict[str, Any]:
    """Sync knowledge graph config."""

    result = {"component": "knowledge-graph", "status": "ok", "message": ""}

    if not prefs.features.knowledge_graph:
        result["status"] = "skipped"
        result["message"] = "Knowledge Graph not enabled"
        return result

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
