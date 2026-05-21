"""Plugin management CLI commands.

Usage:
  opencontext plugin list              List installed plugins
  opencontext plugin search [query]    Search remote registry
  opencontext plugin install <name>    Install from registry
  opencontext plugin install <name> --github owner/repo
  opencontext plugin install <name> --url <url>
  opencontext plugin remove <name>     Remove a plugin
  opencontext plugin update [name]     Check/apply updates
  opencontext plugin info <name>       Show plugin details
  opencontext plugin enable <name>     Enable a plugin
  opencontext plugin disable <name>    Disable a plugin
"""

from __future__ import annotations

import json
from typing import Any

from opencontext_core.plugin_system import (
    PluginInstaller,
    PluginRegistry,
    PluginUpdater,
    RegistryFetcher,
)
from opencontext_core.state import StateStore


def add_plugin_parser(subparsers: Any) -> None:
    """Add plugin command parsers."""

    plugin_parser = subparsers.add_parser(
        "plugin", help="Manage OpenContext plugins."
    )
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_command", required=True)

    # List
    list_parser = plugin_sub.add_parser("list", help="List installed plugins.")
    list_parser.add_argument(
        "--json", action="store_true", help="Output as JSON."
    )

    # Search
    search_parser = plugin_sub.add_parser("search", help="Search available plugins.")
    search_parser.add_argument("query", nargs="?", default="", help="Search query.")
    search_parser.add_argument(
        "--registry", default="", help="Custom registry URL."
    )
    search_parser.add_argument(
        "--refresh", action="store_true", help="Force refresh registry cache."
    )

    # Install
    install_parser = plugin_sub.add_parser("install", help="Install a plugin.")
    install_parser.add_argument("name", help="Plugin name.")
    install_parser.add_argument(
        "--github", default="", help="Install from GitHub (owner/repo)."
    )
    install_parser.add_argument(
        "--url", default="", help="Install from URL."
    )
    install_parser.add_argument(
        "--ver", default="", help="Specific version to install (e.g. 0.1.0)."
    )
    install_parser.add_argument(
        "--registry", default="", help="Custom registry URL."
    )

    # Remove
    remove_parser = plugin_sub.add_parser("remove", help="Remove a plugin.")
    remove_parser.add_argument("name", help="Plugin name.")

    # Update
    update_parser = plugin_sub.add_parser("update", help="Check and apply plugin updates.")
    update_parser.add_argument("name", nargs="?", default="", help="Plugin name (all if omitted).")

    # Info
    info_parser = plugin_sub.add_parser("info", help="Show plugin details.")
    info_parser.add_argument("name", help="Plugin name.")

    # Enable/Disable
    enable_parser = plugin_sub.add_parser("enable", help="Enable a plugin.")
    enable_parser.add_argument("name", help="Plugin name.")

    disable_parser = plugin_sub.add_parser("disable", help="Disable a plugin.")
    disable_parser.add_argument("name", help="Plugin name.")


def handle_plugin(args: Any) -> None:
    """Handle plugin commands."""

    command = getattr(args, "plugin_command", None) or getattr(args, "command", None)

    if command == "list":
        _plugin_list(args)
    elif command == "search":
        _plugin_search(args)
    elif command == "install":
        _plugin_install(args)
    elif command == "remove":
        _plugin_remove(args)
    elif command == "update":
        _plugin_update(args)
    elif command == "info":
        _plugin_info(args)
    elif command == "enable":
        _plugin_enable(args)
    elif command == "disable":
        _plugin_disable(args)


def _plugin_list(args: Any) -> None:
    """List installed plugins."""

    registry = PluginRegistry()
    plugins = registry.discover()

    if args.json:
        data = [
            {
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "enabled": p.enabled,
                "source": p.install_source,
                "installed_at": p.installed_at,
            }
            for p in plugins
        ]
        print(json.dumps(data, indent=2))
        return

    if not plugins:
        print("\n  No plugins installed.")
        print(f"  Plugin directory: {registry.plugins_dir}")
        print()
        print("  Search available:  opencontext plugin search")
        print("  Install plugin:    opencontext plugin install <name>")
        print("  Install from GH:   opencontext plugin install <name> --github owner/repo")
        return

    print()
    # Header
    print(f"  {'Name':<22} {'Version':<10} {'Source':<12} {'Status':<10} {'Description'}")
    print(f"  {'─'*22} {'─'*10} {'─'*12} {'─'*10} {'─'*50}")
    for p in plugins:
        status = "✓ enabled" if p.enabled else "○ disabled"
        source = {"local": "local", "registry": "registry", "github": "GitHub", "url": "URL"}.get(
            p.install_source, p.install_source
        )
        print(f"  {p.name:<22} {p.version:<10} {source:<12} {status:<10} {p.description[:50]}")
    print(f"\n  {len(plugins)} plugin(s) installed")
    print(f"  Directory: {registry.plugins_dir}")


def _plugin_search(args: Any) -> None:
    """Search remote registry for plugins."""

    fetcher = RegistryFetcher(registry_url=args.registry) if args.registry else RegistryFetcher()

    try:
        results = fetcher.search(query=args.query, force=args.refresh)
    except Exception as e:
        print(f"\n  Error fetching registry: {e}")
        print("  Falling back to built-in registry...")
        results = fetcher.search(query=args.query)

    if not results:
        if args.query:
            print(f"\n  No plugins matching '{args.query}' found.")
        else:
            print("\n  No plugins available in registry.")
        return

    print()
    if args.query:
        print(f"  Search results for '{args.query}':")
    else:
        print("  Available plugins:")
    print()

    for p in results:
        latest = p.versions[0].version if p.versions else "—"
        print(f"  {p.name:<22} v{latest:<12} {p.description}")
        if p.homepage:
            print(f"  {'':22}   {p.homepage}")
        print()

    print(f"  {len(results)} plugin(s) available")
    print()
    print("  Install:  opencontext plugin install <name>")
    print("  Details:  opencontext plugin info <name>")


def _plugin_install(args: Any) -> None:
    """Install a plugin."""

    installer = PluginInstaller()

    # GitHub install
    if args.github:
        print(f"\n  Installing from GitHub: {args.github}")
        result = installer.install_from_github(args.github, name=args.name)
    # URL install
    elif args.url:
        print(f"\n  Installing from URL: {args.url}")
        result = installer.install_from_url(args.name, args.url)
    # Registry install
    else:
        version = args.ver or None
        result = installer.install_from_registry(args.name, version=version)

    _print_install_result(result)


def _plugin_remove(args: Any) -> None:
    """Remove a plugin."""

    registry = PluginRegistry()

    # Verify it exists
    info = registry.get_info(args.name)
    if info is None:
        print(f"\n  Plugin '{args.name}' not found.")
        print(f"  Installed plugins: {', '.join(p.name for p in registry.discover())}")
        return

    print(f"\n  Removing '{args.name}'...")

    # Auto-backup plugin before removal
    plugin_dir = registry.plugins_dir / args.name
    backup_dir = plugin_dir.parent / f".{args.name}.bak"
    if plugin_dir.exists():
        import shutil
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        shutil.copytree(plugin_dir, backup_dir)

    if registry.remove(args.name):
        # Clean up backup
        if backup_dir.exists():
            import shutil
            shutil.rmtree(backup_dir)
        print(f"  ✓ '{args.name}' removed.\n")
    else:
        # Restore from backup
        if backup_dir.exists():
            import shutil
            plugin_dir.mkdir(parents=True, exist_ok=True)
            for item in backup_dir.iterdir():
                shutil.copy2(item, plugin_dir / item.name)
            shutil.rmtree(backup_dir)
        print(f"  ✗ Failed to remove '{args.name}'.\n")


def _plugin_update(args: Any) -> None:
    """Check and apply plugin updates."""

    updater = PluginUpdater()

    if args.name:
        print(f"\n  Checking updates for '{args.name}'...")
        result = updater.check_updates_for(args.name)
        _print_install_result(result)
        return

    # Check all
    print("\n  Checking all plugins for updates...")
    results = updater.check_updates()

    updated = [r for r in results if r.status == "updated"]
    skipped = [r for r in results if r.status == "skipped"]
    failed = [r for r in results if r.status == "failed"]

    print()
    for r in results:
        icon = {"updated": "✓", "skipped": "·", "failed": "✗"}.get(r.status, "?")
        print(f"  {icon} {r.message}")

    print()
    if updated:
        print(f"  {len(updated)} plugin(s) updated.")
    if skipped:
        print(f"  {len(skipped)} plugin(s) up to date.")
    if failed:
        print(f"  {len(failed)} plugin(s) failed to update.")
        for r in failed:
            if r.error:
                print(f"    {r.name}: {r.error}")
    if not updated and not failed:
        print("  All plugins up to date.")
    print()


def _plugin_info(args: Any) -> None:
    """Show plugin details."""

    registry = PluginRegistry()
    info = registry.get_info(args.name)

    if info is None:
        # Check registry
        fetcher = RegistryFetcher()
        entry = fetcher.get(args.name)
        if entry:
            print(f"\n  {entry.name}")
            print(f"  {'─' * len(entry.name)}")
            print(f"  Description: {entry.description}")
            print(f"  Author:      {entry.author or '—'}")
            print(f"  Homepage:    {entry.homepage or '—'}")
            print(f"  Repository:  {entry.repository or '—'}")
            if entry.versions:
                print(f"  Versions:    {', '.join(v.version for v in entry.versions)}")
            print()
            print(f"  Not installed. Install with: opencontext plugin install {args.name}")
            return
        print(f"\n  Plugin '{args.name}' not found locally or in registry.\n")
        return

    print(f"\n  {info.name}")
    print(f"  {'─' * len(info.name)}")
    print(f"  Version:      {info.version}")
    print(f"  Description:  {info.description}")
    print(f"  Author:       {info.author or '—'}")
    print(f"  Homepage:     {info.homepage or '—'}")
    print(f"  Repository:   {info.repository or '—'}")
    print(f"  Status:       {'✓ enabled' if info.enabled else '○ disabled'}")
    print(f"  Source:       {info.install_source}")
    print(f"  Source URL:   {info.source_url or '—'}")
    print(f"  Entry point:  {info.entry_point}")
    print(f"  Installed at: {info.installed_at or '—'}")
    print(f"  Updated at:   {info.updated_at or '—'}")
    if info.hooks:
        print(f"  Hooks:        {', '.join(info.hooks)}")
    print()


def _plugin_enable(args: Any) -> None:
    """Enable a plugin."""

    registry = PluginRegistry()
    if registry.enable(args.name):
        print(f"  ✓ '{args.name}' enabled.\n")
    else:
        print(f"  ✗ Plugin '{args.name}' not found.\n")


def _plugin_disable(args: Any) -> None:
    """Disable a plugin."""

    registry = PluginRegistry()
    if registry.disable(args.name):
        print(f"  ○ '{args.name}' disabled.\n")
    else:
        print(f"  ✗ Plugin '{args.name}' not found.\n")


def _print_install_result(result: Any) -> None:
    """Pretty-print an install result."""

    icons = {
        "installed": "✓",
        "updated": "✓",
        "skipped": "·",
        "failed": "✗",
    }
    icon = icons.get(result.status, "?")

    print()
    print(f"  {icon} {result.message}")
    if result.source:
        print(f"     Source: {result.source}")
    if result.error:
        print(f"     Error:  {result.error}")
    print()
