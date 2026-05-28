"""Bridges CLI command — scan and display cross-language bridge boundaries."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from rich.console import Console
from rich.table import Table

from opencontext_core.indexing.bridge_detector import BridgeDetector

console = Console()


def add_bridges_parser(subparsers: Any) -> None:
    """Add bridges command parser."""
    bridges_parser = subparsers.add_parser(
        "bridges",
        help="Detect cross-language call boundaries in your project.",
    )
    bridges_sub = bridges_parser.add_subparsers(dest="bridges_command", required=True)

    scan_parser = bridges_sub.add_parser("scan", help="Scan project for cross-language bridges.")
    scan_parser.add_argument("root", nargs="?", default=".", help="Project root to scan.")
    scan_parser.add_argument(
        "--type",
        default=None,
        choices=["HTTP", "GRPC", "CLI_SUBPROCESS", "IPC"],
        help="Filter by bridge type.",
    )
    scan_parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Minimum confidence threshold (0.0–1.0).",
    )
    scan_parser.add_argument(
        "--json",
        action="store_true",
        dest="json",
        help="Output as JSON.",
    )

    show_parser = bridges_sub.add_parser("show", help="Show bridges for a specific symbol or file.")
    show_parser.add_argument("symbol", help="Symbol name or file path fragment to filter by.")
    show_parser.add_argument("root", nargs="?", default=".", help="Project root to scan.")


def handle_bridges(args: Any) -> None:
    """Handle bridges commands."""
    command = args.bridges_command
    root = getattr(args, "root", ".")

    if command == "scan":
        _handle_scan(
            root,
            bridge_type=getattr(args, "type", None),
            min_confidence=getattr(args, "min_confidence", 0.0),
            output_json=getattr(args, "json", False),
        )
    elif command == "show":
        _handle_show(root, symbol=args.symbol)


def _handle_scan(
    root: str,
    bridge_type: str | None = None,
    min_confidence: float = 0.0,
    output_json: bool = False,
) -> None:
    """Scan and display all detected bridges."""
    with console.status("[bold green]Scanning for cross-language bridges..."):
        detector = BridgeDetector()
        bridges = detector.scan(root)

    if bridge_type:
        bridges = [b for b in bridges if b.bridge_type == bridge_type]
    if min_confidence > 0:
        bridges = [b for b in bridges if b.confidence >= min_confidence]

    if not bridges:
        console.print("[dim]No cross-language bridges detected.[/]")
        return

    if output_json:
        print(json.dumps([dataclasses.asdict(b) for b in bridges], indent=2))
        return

    table = Table(title=f"Cross-Language Bridges ({len(bridges)} found)")
    table.add_column("File", style="cyan", max_width=40)
    table.add_column("Line", justify="right")
    table.add_column("Type", style="yellow")
    table.add_column("Confidence", justify="right")
    table.add_column("Target Hint", max_width=40)

    for b in bridges:
        conf_style = (
            "green" if b.confidence >= 0.85 else ("yellow" if b.confidence >= 0.7 else "dim")
        )
        table.add_row(
            b.source_file,
            str(b.line),
            b.bridge_type,
            f"[{conf_style}]{b.confidence:.0%}[/]",
            b.target_hint,
        )

    console.print(table)

    type_counts: dict[str, int] = {}
    for b in bridges:
        type_counts[b.bridge_type] = type_counts.get(b.bridge_type, 0) + 1
    summary = " | ".join(f"{t}: {c}" for t, c in sorted(type_counts.items()))
    console.print(f"[dim]By type: {summary}[/]")


def _handle_show(root: str, symbol: str) -> None:
    """Show bridges filtered by symbol or file path fragment."""
    detector = BridgeDetector()
    bridges = detector.scan(root)
    sym = symbol.lower()
    filtered = [
        b
        for b in bridges
        if sym in b.source_file.lower()
        or sym in b.bridge_type.lower()
        or sym in b.target_hint.lower()
    ]

    if not filtered:
        console.print(f"[dim]No bridges found matching '{symbol}'.[/]")
        return

    table = Table(title=f"Bridges matching '{symbol}'")
    table.add_column("File", style="cyan")
    table.add_column("Line", justify="right")
    table.add_column("Type", style="yellow")
    table.add_column("Target Hint")

    for b in filtered:
        table.add_row(b.source_file, str(b.line), b.bridge_type, b.target_hint)

    console.print(table)
