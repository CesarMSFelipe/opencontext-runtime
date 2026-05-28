"""Extension CLI command — search, install, list, and remove workflow extensions."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table

from opencontext_core.workflow.extension_registry import ExtensionRegistry

console = Console()


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
    if not results:
        console.print("[yellow]No extensions found.[/]")
        return

    if output_json:
        print(json.dumps(results, indent=2))
        return

    table = Table(title=f"Extensions ({len(results)} found)")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Description")
    table.add_column("Tags")
    for ext in results:
        table.add_row(
            ext.get("name", ""),
            ext.get("version", ""),
            ext.get("description", ""),
            ", ".join(ext.get("tags", [])),
        )
    console.print(table)


def _handle_install(registry: ExtensionRegistry, name: str, root: str) -> None:
    try:
        path = registry.install(name, root=root)
        console.print(f"[green]✓ Installed extension '{name}' to {path}[/]")
    except ValueError as e:
        console.print(f"[red]Error: {e}[/]")


def _handle_list(registry: ExtensionRegistry, root: str) -> None:
    installed = registry.list_installed(root=root)
    if not installed:
        console.print(
            "[dim]No extensions installed. Use 'opencontext extension search' to find some.[/]"
        )
        return

    table = Table(title="Installed Extensions")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Author")
    table.add_column("Description")
    for m in installed:
        table.add_row(m.name, m.version, m.author, m.description)
    console.print(table)


def _handle_info(registry: ExtensionRegistry, name: str) -> None:
    matches = [e for e in registry.search() if e.get("name") == name]
    if not matches:
        console.print(f"[red]Extension not found: {name}[/]")
        return
    ext = matches[0]
    from rich.panel import Panel

    content = "\n".join(
        [
            f"[bold]Name:[/]        {ext.get('name', '')}",
            f"[bold]Version:[/]     {ext.get('version', '')}",
            f"[bold]Author:[/]      {ext.get('author', '')}",
            f"[bold]Description:[/] {ext.get('description', '')}",
            f"[bold]Tags:[/]        {', '.join(ext.get('tags', []))}",
            f"[bold]Requires:[/]    opencontext-core >= {ext.get('requires_version', 'any')}",
        ]
    )
    console.print(Panel(content, title=f"Extension: {name}", border_style="cyan"))


def _handle_remove(registry: ExtensionRegistry, name: str, root: str) -> None:
    removed = registry.remove(name, root=root)
    if removed:
        console.print(f"[green]✓ Removed extension '{name}'[/]")
    else:
        console.print(f"[yellow]Extension '{name}' not found (already removed?)[/]")
