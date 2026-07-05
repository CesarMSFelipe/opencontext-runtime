"""Routes CLI command — detect and display framework route definitions."""

from __future__ import annotations

import json as _json
from typing import Any

from opencontext_core.dx.console_styles import console
from opencontext_core.indexing.framework_router import FrameworkRouter


def add_routes_parser(subparsers: Any) -> None:
    routes_parser = subparsers.add_parser(
        "routes",
        help="Detect framework route definitions (Django, FastAPI, Flask, Express, NestJS).",
    )
    routes_sub = routes_parser.add_subparsers(dest="routes_command")
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
    command = getattr(args, "routes_command", None)
    root = getattr(args, "root", ".")

    if command is None:
        import subprocess

        subprocess.run(["opencontext", "routes", "--help"])
        return

    if command == "scan":
        _handle_scan(
            root,
            framework=getattr(args, "framework", None),
            output_json=getattr(args, "output_json", False),
        )


def _handle_scan(root: str, framework: str | None = None, output_json: bool = False) -> None:
    with console.status("Scanning for routes..."):
        router = FrameworkRouter()
        routes = router.scan(root)
    if framework:
        routes = [r for r in routes if r.framework == framework]

    if output_json:
        import dataclasses

        print(_json.dumps([dataclasses.asdict(r) for r in routes], indent=2))
        return

    console.header("Routes")
    if not routes:
        console.info("No routes yet.")
        return

    rows = [
        [r.source_file, str(r.line), r.framework, r.method, r.path_pattern, r.handler]
        for r in routes
    ]
    console.table(
        f"Routes ({len(routes)} found)",
        ["File", "Line", "Framework", "Method", "Path", "Handler"],
        rows,
    )
    fw_counts: dict[str, int] = {}
    for r in routes:
        fw_counts[r.framework] = fw_counts.get(r.framework, 0) + 1
    summary = " | ".join(f"{fw}: {c}" for fw, c in sorted(fw_counts.items()))
    console.dim(f"By framework: {summary}")
