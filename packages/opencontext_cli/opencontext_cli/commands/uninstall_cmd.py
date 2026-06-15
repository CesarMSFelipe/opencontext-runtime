"""Uninstall CLI command — cleanly remove OpenContext's managed agent config.

The inverse of ``setup``: strips the managed instructions block and the
``opencontext`` MCP entry (plus agent-specific extras) from each agent, leaving
everything the developer authored untouched. A pre-change backup is taken, so a
removal is recoverable.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from opencontext_core.configurator import KNOWN_AGENTS, Configurator

console = Console()


def add_uninstall_parser(subparsers: Any) -> None:
    """Add the ``uninstall`` command parser."""
    parser = subparsers.add_parser(
        "uninstall",
        help="Remove OpenContext's managed config from your AI agent(s).",
        description=(
            "Remove OpenContext from existing AI coding agents (the inverse of setup).\n\n"
            "  opencontext uninstall                 Remove from every configured agent\n"
            "  opencontext uninstall claude-code      Remove from one agent\n"
            "  opencontext uninstall --all            Remove from every known agent\n"
            "  opencontext uninstall --dry-run        Show what would be removed\n\n"
            "Only OpenContext's managed instructions block and MCP entry are removed; "
            "your own content is left intact and a backup is taken first."
        ),
    )
    parser.add_argument("agents", nargs="*", metavar="AGENT", help="Agent id(s) to remove from.")
    parser.add_argument(
        "--all", dest="all_agents", action="store_true", help="Remove from every known agent."
    )
    parser.add_argument(
        "--scope", choices=["global", "local"], default="local", help="Where config was written."
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation.")
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview the removal without changing anything."
    )


def handle_uninstall(args: Any) -> None:
    """Remove OpenContext's managed config from the requested agents."""
    from opencontext_cli.main import _resolve_flag

    scope = getattr(args, "scope", "local")
    dry_run = _resolve_flag(getattr(args, "dry_run", False), "OPENCONTEXT_DRY_RUN")
    json_output = _resolve_flag(getattr(args, "json", False), "OPENCONTEXT_JSON")
    yes = _resolve_flag(getattr(args, "yes", False), "OPENCONTEXT_YES")

    configurator = Configurator(project_root=getattr(args, "root", "."))

    requested = _parse_agents(getattr(args, "agents", None))
    if getattr(args, "all_agents", False):
        agents = list(KNOWN_AGENTS)
    elif requested:
        agents = requested
    else:
        agents = configurator.detect_installed()

    valid = [a for a in agents if a in set(KNOWN_AGENTS)]
    unknown = [a for a in agents if a not in set(KNOWN_AGENTS)]

    if not valid:
        if json_output:
            print(json.dumps({"status": "no_agents", "agents_removed": 0, "skipped": unknown}))
        else:
            console.print("[yellow]No configured agents to remove.[/]")
        return

    if dry_run:
        report = configurator.deconfigure(valid, scope=scope, dry_run=True)
        if json_output:
            print(json.dumps(report, indent=2))
        else:
            console.print("[bold yellow]Dry run — nothing removed.[/]")
            for result in report["results"]:
                console.print(f"  [bold]{result['agent']}[/]")
                for action in result.get("plan", []):
                    console.print(f"    [dim]{action}[/]")
        return

    # Destructive: require explicit confirmation unless --yes (or non-interactive
    # JSON). Never proceed silently on a non-TTY without --yes.
    if not yes and not json_output:
        if not sys.stdin.isatty():
            console.print("[yellow]Refusing non-interactive uninstall; pass --yes.[/]")
            return
        console.print(f"About to remove OpenContext from: [bold]{', '.join(valid)}[/]")
        if not Confirm.ask("Proceed?", default=False):
            console.print("[yellow]Uninstall cancelled.[/]")
            return

    report = configurator.deconfigure(valid, scope=scope)
    if unknown:
        report["skipped"] = unknown
    if json_output:
        print(json.dumps(report, indent=2))
        return
    removed_n = report["agents_removed"]
    console.print(
        Panel.fit(
            f"[bold green]Removed OpenContext from {removed_n} agent(s)[/bold green]",
            border_style="green",
        )
    )
    for result in report.get("results", []):
        console.print(f"  [bold]{result['agent']}[/]")
        for file_path in result.get("files", []):
            console.print(f"    [dim]{file_path}[/]")
    for agent in unknown:
        console.print(f"  [yellow]- {agent} (unknown, skipped)[/]")


def _parse_agents(values: list[str] | None) -> list[str]:
    if not values:
        return []
    agents: list[str] = []
    for raw in values:
        for item in raw.split(","):
            normalized = item.strip()
            if normalized and normalized not in agents:
                agents.append(normalized)
    return agents
