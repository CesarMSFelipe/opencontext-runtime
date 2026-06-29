"""Bridges CLI command — scan and display cross-language bridge boundaries."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from opencontext_core.dx.console_styles import console
from opencontext_core.indexing.bridge_detector import BridgeDetector


def add_bridges_parser(subparsers: Any) -> None:
    """Add bridges command parser."""
    bridges_parser = subparsers.add_parser(
        "bridges",
        help="Detect cross-language call boundaries in your project.",
    )
    bridges_sub = bridges_parser.add_subparsers(dest="bridges_command")

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
        help="Minimum confidence threshold (0.0-1.0).",
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
    command = getattr(args, "bridges_command", None)
    root = getattr(args, "root", ".")

    if command is None:
        import subprocess

        subprocess.run(["opencontext", "bridges", "--help"])
        return

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
    detector = BridgeDetector()
    # Skip the live spinner under --json (keep stdout pure) and when rich is absent.
    if output_json or not console.available:
        bridges = detector.scan(root)
    else:
        with console.status("Scanning for cross-language bridges..."):
            bridges = detector.scan(root)

    if bridge_type:
        bridges = [b for b in bridges if b.bridge_type == bridge_type]
    if min_confidence > 0:
        bridges = [b for b in bridges if b.confidence >= min_confidence]

    if output_json:
        print(json.dumps([dataclasses.asdict(b) for b in bridges], indent=2))  # pure JSON
        return

    console.header("Cross-Language Bridges")
    if not bridges:
        console.info("No cross-language bridges detected yet.")
        return

    rows = [
        [b.source_file, str(b.line), b.bridge_type, f"{b.confidence:.0%}", b.target_hint]
        for b in bridges
    ]
    console.table(
        f"Bridges ({len(bridges)} found)",
        ["File", "Line", "Type", "Confidence", "Target Hint"],
        rows,
    )

    type_counts: dict[str, int] = {}
    for b in bridges:
        type_counts[b.bridge_type] = type_counts.get(b.bridge_type, 0) + 1
    summary = " | ".join(f"{t}: {c}" for t, c in sorted(type_counts.items()))
    console.dim(f"By type: {summary}")


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

    console.header(f"Bridges: {symbol}")
    if not filtered:
        console.info(f"No bridges found matching '{symbol}' yet.")
        return

    rows = [[b.source_file, str(b.line), b.bridge_type, b.target_hint] for b in filtered]
    console.table(
        f"Bridges matching '{symbol}'",
        ["File", "Line", "Type", "Target Hint"],
        rows,
    )
