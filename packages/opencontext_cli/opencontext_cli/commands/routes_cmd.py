"""Routes CLI command — detect and display framework route definitions."""

from __future__ import annotations

import json as _json
from typing import Any

from rich.console import Console
from rich.table import Table

from opencontext_core.indexing.framework_router import FrameworkRouter

console = Console()


def add_routes_parser(subparsers: Any) -> None:
    routes_parser = subparsers.add_parser(
        "routes",
        help="Detect framework route definitions (Django, FastAPI, Flask, Express, NestJS).",
    )
    routes_sub = routes_parser.add_subparsers(dest="routes_command", required=True)
    scan_parser = routes_sub.add_parser("scan", help="Scan project for route definitions.")
    scan_parser.add_argument("root", nargs="?", default=".", help="Project root.")
    scan_parser.add_argument(
        "--framework",
        default=None,
        choices=["django", "fastapi", "flask", "express", "nestjs"],
        help="Filter by framework.",
    )
    scan_parser.add_argument(
        "--json", action="store_true", dest="output_json", help="Output as JSON."
    )


def handle_routes(args: Any) -> None:
    command = args.routes_command
    root = getattr(args, "root", ".")
    if command == "scan":
        _handle_scan(
            root,
            framework=getattr(args, "framework", None),
            output_json=getattr(args, "output_json", False),
        )


def _handle_scan(root: str, framework: str | None = None, output_json: bool = False) -> None:
    with console.status("[bold green]Scanning for routes..."):
        router = FrameworkRouter()
        routes = router.scan(root)
    if framework:
        routes = [r for r in routes if r.framework == framework]
    if not routes:
        console.print("[dim]No route definitions detected.[/]")
        return
    if output_json:
        import dataclasses

        print(_json.dumps([dataclasses.asdict(r) for r in routes], indent=2))
        return
    table = Table(title=f"Routes ({len(routes)} found)")
    table.add_column("File", style="cyan", max_width=40)
    table.add_column("Line", justify="right")
    table.add_column("Framework", style="yellow")
    table.add_column("Method", style="green")
    table.add_column("Path")
    table.add_column("Handler")
    for r in routes:
        table.add_row(r.source_file, str(r.line), r.framework, r.method, r.path_pattern, r.handler)
    console.print(table)
    fw_counts: dict[str, int] = {}
    for r in routes:
        fw_counts[r.framework] = fw_counts.get(r.framework, 0) + 1
    summary = " | ".join(f"{fw}: {c}" for fw, c in sorted(fw_counts.items()))
    console.print(f"[dim]By framework: {summary}[/]")
