"""Telemetry CLI command — show cumulative token savings."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()


def add_telemetry_parser(subparsers: Any) -> None:
    tel_parser = subparsers.add_parser("telemetry", help="Token savings telemetry.")
    tel_sub = tel_parser.add_subparsers(dest="telemetry_command", required=True)
    show_parser = tel_sub.add_parser("show", help="Show cumulative token savings.")
    show_parser.add_argument("--root", default=".", help="Project root.")
    show_parser.add_argument("--last", type=int, default=None, help="Show only last N events.")
    tel_sub.add_parser("clear", help="Clear telemetry data.").add_argument("--root", default=".")


def handle_telemetry(args: Any) -> None:
    command = args.telemetry_command
    root = getattr(args, "root", ".")
    if command == "show":
        _handle_show(root, last=getattr(args, "last", None))
    elif command == "clear":
        _handle_clear(root)


def _handle_show(root: str, last: int | None = None) -> None:
    from opencontext_core.evaluation.telemetry import load_telemetry

    store = load_telemetry(root)
    if not store.events:
        console.print(
            "[dim]No telemetry data yet. "
            "Run 'opencontext pack . --query <task>' to start tracking.[/]"
        )
        return

    events = store.events[-last:] if last else store.events

    console.print(f"\n[bold]Token Savings Summary[/] — {len(store.events)} total events\n")
    console.print(f"  Total tokens saved : [green]{store.total_saved:>10,}[/]")
    console.print(f"  Avg reduction      : [green]{store.average_reduction:>9.1f}%[/]")
    console.print(f"  Naive total        :         {store.total_naive:>10,}")
    console.print(f"  Optimized total    :         {store.total_optimized:>10,}")
    console.print()

    table = Table(title=f"Recent Events ({len(events)})", box=None)
    table.add_column("Scenario")
    table.add_column("Naive", justify="right")
    table.add_column("Optimized", justify="right")
    table.add_column("Reduction", justify="right")
    for e in reversed(events):
        table.add_row(
            e.scenario or e.task[:50],
            f"{e.naive_tokens:,}",
            f"{e.optimized_tokens:,}",
            f"[green]{e.reduction_pct:.1f}%[/]",
        )
    console.print(table)


def _handle_clear(root: str) -> None:
    from pathlib import Path

    path = Path(root) / ".opencontext/telemetry.json"
    if path.exists():
        path.unlink()
        console.print("[green]✓ Telemetry cleared.[/]")
    else:
        console.print("[dim]No telemetry data to clear.[/]")
