"""Extension CLI command — search, install, list, and remove workflow extensions."""

from __future__ import annotations

import json
import sys
from typing import Any

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console
from opencontext_core.workflow.extension_registry import ExtensionRegistry


def add_extension_parser(subparsers: Any) -> None:
    """Add extension command parser."""
    ext_parser = subparsers.add_parser(
        "extension",
        help="Manage OpenContext workflow extensions.",
    )
    ext_sub = ext_parser.add_subparsers(dest="extension_command", required=True)

    search_parser = ext_sub.add_parser("search", help="Search available extensions.")
    search_parser.add_argument("query", nargs="?", default="", help="Search query.")
    search_parser.add_argument(
        "--json",
        action="store_true",
        dest="json",
        help="Output as JSON.",
    )

    install_parser = ext_sub.add_parser("install", help="Install an extension.")
    install_parser.add_argument("name", help="Extension name to install.")
    install_parser.add_argument("--root", default=".", help="Project root.")

    list_parser = ext_sub.add_parser("list", help="List installed extensions.")
    list_parser.add_argument("--root", default=".", help="Project root.")

    info_parser = ext_sub.add_parser("info", help="Show details for an available extension.")
    info_parser.add_argument("name", help="Extension name.")

    remove_parser = ext_sub.add_parser("remove", help="Remove an installed extension.")
    remove_parser.add_argument("name", help="Extension name to remove.")
    remove_parser.add_argument("--root", default=".", help="Project root.")


def handle_extension(args: Any) -> None:
    """Handle extension commands."""
    command = args.extension_command
    registry = ExtensionRegistry()
    root = getattr(args, "root", ".")

    if command == "search":
        _handle_search(
            registry, getattr(args, "query", ""), output_json=getattr(args, "json", False)
        )
    elif command == "install":
        _handle_install(registry, args.name, root)
    elif command == "list":
        _handle_list(registry, root)
    elif command == "info":
        _handle_info(registry, args.name)
    elif command == "remove":
        _handle_remove(registry, args.name, root)


def _handle_search(registry: ExtensionRegistry, query: str, output_json: bool = False) -> None:
    results = registry.search(query)
    if output_json:
        print(json.dumps(results, indent=2))  # pure JSON to stdout
        return

    console.header("Extension Search")
    if not results:
        console.info("No extensions yet.")
        return

    rows = [
        [
            ext.get("name", ""),
            ext.get("version", ""),
            ext.get("description", ""),
            ", ".join(ext.get("tags", [])),
        ]
        for ext in results
    ]
    console.table(
        f"Extensions ({len(results)} found)",
        ["Name", "Version", "Description", "Tags"],
        rows,
    )


def _handle_install(registry: ExtensionRegistry, name: str, root: str) -> None:
    try:
        path = registry.install(name, root=root)
    except ValueError as e:
        eprint(str(e))
        sys.exit(1)
    console.success(f"Installed extension '{name}' to {path}")


def _handle_list(registry: ExtensionRegistry, root: str) -> None:
    installed = registry.list_installed(root=root)
    console.header("Installed Extensions")
    if not installed:
        console.info("No extensions installed yet.")
        console.dim("Find some:  opencontext extension search")
        return

    rows = [[m.name, m.version, m.author, m.description] for m in installed]
    console.table("Extensions", ["Name", "Version", "Author", "Description"], rows)


def _handle_info(registry: ExtensionRegistry, name: str) -> None:
    matches = [e for e in registry.search() if e.get("name") == name]
    if not matches:
        eprint(f"Extension not found: {name}")
        sys.exit(1)
    ext = matches[0]
    console.header(f"Extension: {name}")
    console.print(f"  Name:        {ext.get('name', '')}")
    console.print(f"  Version:     {ext.get('version', '')}")
    console.print(f"  Author:      {ext.get('author', '')}")
    console.print(f"  Description: {ext.get('description', '')}")
    console.print(f"  Tags:        {', '.join(ext.get('tags', []))}")
    console.print(f"  Requires:    opencontext-core >= {ext.get('requires_version', 'any')}")


def _handle_remove(registry: ExtensionRegistry, name: str, root: str) -> None:
    removed = registry.remove(name, root=root)
    if removed:
        console.success(f"Removed extension '{name}'")
    else:
        console.warning(f"Extension '{name}' not found (already removed?)")
