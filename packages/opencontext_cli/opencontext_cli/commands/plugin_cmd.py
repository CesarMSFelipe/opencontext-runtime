"""Plugin management CLI commands.

Usage:
  opencontext plugin list              List installed plugins
  opencontext plugin search [query]    Search remote registry
  opencontext plugin init <name>       Scaffold a new plugin
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
from pathlib import Path
from typing import Any

from opencontext_core.dx.console_styles import BrandConsole, console
from opencontext_core.plugin_system import (
    PluginInstaller,
    PluginRegistry,
    PluginUpdater,
    RegistryFetcher,
)


def _stderr_console() -> BrandConsole:
    """Brand console bound to STDERR so error lines never pollute stdout/JSON."""
    bc = BrandConsole()
    inner = getattr(bc, "_console", None)
    if inner is not None:
        from rich.console import Console as _Console

        bc._console = _Console(stderr=True)
    return bc


err_console = _stderr_console()


def add_plugin_parser(subparsers: Any) -> None:
    """Add plugin command parsers."""

    plugin_parser = subparsers.add_parser("plugin", help="Manage OpenContext plugins.")
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_command", required=True)

    list_parser = plugin_sub.add_parser("list", help="List installed plugins.")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON.")

    search_parser = plugin_sub.add_parser("search", help="Search available plugins.")
    search_parser.add_argument("query", nargs="?", default="", help="Search query.")
    search_parser.add_argument("--registry", default="", help="Custom registry URL.")
    search_parser.add_argument(
        "--refresh", action="store_true", help="Force refresh registry cache."
    )

    init_parser = plugin_sub.add_parser("init", help="Scaffold a new plugin.")
    init_parser.add_argument("name", help="Plugin name (alphanumeric + hyphens).")
    init_parser.add_argument("--description", default="", help="Short plugin description.")
    init_parser.add_argument("--author", default="", help="Plugin author name.")
    init_parser.add_argument(
        "--template",
        choices=["basic", "advanced"],
        default="basic",
        help="Scaffold template to use (default: basic).",
    )

    install_parser = plugin_sub.add_parser("install", help="Install a plugin.")
    install_parser.add_argument("name", help="Plugin name.")
    install_parser.add_argument("--github", default="", help="Install from GitHub (owner/repo).")
    install_parser.add_argument("--url", default="", help="Install from URL.")
    install_parser.add_argument(
        "--ver", default="", help="Specific version to install (e.g. 0.1.0)."
    )
    install_parser.add_argument("--registry", default="", help="Custom registry URL.")
    install_parser.add_argument(
        "--marketplace",
        default="",
        help="Install a marketplace bundle (archive or dir) with full enforcement.",
    )
    install_parser.add_argument(
        "--key", default="", help="Signing/verification key for a marketplace bundle."
    )

    remove_parser = plugin_sub.add_parser("remove", help="Remove a plugin.")
    remove_parser.add_argument("name", help="Plugin name.")

    update_parser = plugin_sub.add_parser("update", help="Check and apply plugin updates.")
    update_parser.add_argument("name", nargs="?", default="", help="Plugin name (all if omitted).")

    info_parser = plugin_sub.add_parser("info", help="Show plugin details.")
    info_parser.add_argument("name", help="Plugin name.")
    info_parser.add_argument("--json", action="store_true", help="Output as JSON.")

    enable_parser = plugin_sub.add_parser("enable", help="Enable a plugin.")
    enable_parser.add_argument("name", help="Plugin name.")

    disable_parser = plugin_sub.add_parser("disable", help="Disable a plugin.")
    disable_parser.add_argument("name", help="Plugin name.")

    # PR-015: lifecycle subcommands over the typed-contract pipeline.
    activate_parser = plugin_sub.add_parser(
        "activate", help="Run a plugin through the full lifecycle."
    )
    activate_parser.add_argument("name", help="Plugin name.")
    activate_parser.add_argument("--json", action="store_true", help="Output as JSON.")

    health_parser = plugin_sub.add_parser("health", help="Activate and report plugin health.")
    health_parser.add_argument("name", help="Plugin name.")

    benchmark_parser = plugin_sub.add_parser(
        "benchmark", help="Run the plugin's benchmark gate (before activation)."
    )
    benchmark_parser.add_argument("name", help="Plugin name.")

    # PR-016: marketplace publish flow (build → leak gate → validate → sign).
    publish_parser = plugin_sub.add_parser(
        "publish", help="Build, leak-scan, validate, version, and sign a marketplace package."
    )
    publish_parser.add_argument("src", help="Package source directory (with marketplace.json).")
    publish_parser.add_argument("--key", default="", help="HMAC signing key.")
    publish_parser.add_argument(
        "--allow",
        action="store_true",
        help="Acknowledge and bypass leak-detection findings.",
    )
    publish_parser.add_argument("--out", default="", help="Output directory for the archive.")
    publish_parser.add_argument("--registry", default="", help="Reserved: target registry URL.")


def handle_plugin(args: Any) -> None:
    """Handle plugin commands."""

    command = getattr(args, "plugin_command", None) or getattr(args, "command", None)

    if command == "list":
        _plugin_list(args)
    elif command == "search":
        _plugin_search(args)
    elif command == "init":
        _plugin_init(args)
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
    elif command == "activate":
        _plugin_activate(args)
    elif command == "health":
        _plugin_health(args)
    elif command == "benchmark":
        _plugin_benchmark(args)
    elif command == "publish":
        _plugin_publish(args)


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

    console.header("Installed Plugins")
    if not plugins:
        console.info("No plugins installed.")
        console.dim(f"Plugin directory: {registry.plugins_dir}")
        console.print()
        console.dim("Search available:  opencontext plugin search")
        console.dim("Install plugin:    opencontext plugin install <name>")
        console.dim("Install from GH:   opencontext plugin install <name> --github owner/repo")
        return

    rows = []
    for p in plugins:
        status = "✓ enabled" if p.enabled else "○ disabled"
        source = {"local": "local", "registry": "registry", "github": "GitHub", "url": "URL"}.get(
            p.install_source, p.install_source
        )
        rows.append([p.name, p.version, source, status, p.description[:50]])
    console.table("Plugins", ["Name", "Version", "Source", "Status", "Description"], rows)
    console.dim(f"{len(plugins)} plugin(s) installed · {registry.plugins_dir}")


def _plugin_search(args: Any) -> None:
    """Search remote registry for plugins."""

    fetcher = RegistryFetcher(registry_url=args.registry) if args.registry else RegistryFetcher()

    try:
        results = fetcher.search(query=args.query, force=args.refresh)
    except Exception as e:
        err_console.warning(f"Error fetching registry: {e}")
        console.dim("Falling back to built-in registry...")
        results = fetcher.search(query=args.query)

    title = f"Search: {args.query}" if args.query else "Plugin Registry"
    console.header(title)
    if not results:
        if args.query:
            console.info(f"No plugins matching '{args.query}' yet.")
        else:
            console.info("No plugins available in registry yet.")
        return

    if not args.query:
        console.dim("Planned plugins — not yet published.")

    rows = [
        [p.name, f"v{p.versions[0].version}" if p.versions else "—", p.description]
        for p in results
    ]
    console.table("Available", ["Name", "Version", "Description"], rows)

    console.dim(f"{len(results)} plugin(s) listed")
    console.print()
    console.dim("Custom install:  opencontext plugin install <name> --github owner/repo")
    console.dim("Custom install:  opencontext plugin install <name> --url <url>")
    console.dim("New scaffold:    opencontext plugin install <name>")


def _plugin_init(args: Any) -> None:
    """Scaffold a new plugin directory."""

    name = args.name.strip()
    if not name.replace("-", "").replace("_", "").isalnum():
        err_console.error(
            f"Invalid plugin name: '{name}'. Use alphanumeric, hyphens, or underscores."
        )
        return

    plugin_dir = Path.cwd() / name
    if plugin_dir.exists():
        err_console.error(f"Directory '{name}' already exists.")
        return

    description = args.description or f"Plugin '{name}'"
    author = args.author or ""
    class_name = "".join(part.capitalize() for part in name.replace("-", "_").split("_"))
    if class_name.endswith("Plugin"):
        base_name = class_name
    else:
        base_name = f"{class_name}Plugin"

    plugin_dir.mkdir(parents=True, exist_ok=True)

    # --- plugin.json ---
    # Every loader reads plugin.json (not plugin.yaml); scaffolding YAML broke the
    # create -> use round-trip. Include an empty permissions block so the plugin is
    # managed under the deny-by-default contract; the checksum is stamped below.
    manifest = {
        "name": name,
        "version": "0.1.0",
        "description": description,
        "author": author,
        "entry_point": "plugin.py",
        "hooks": [],
        "enabled": True,
        "permissions": {},
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    console.success(f"Created {name}/plugin.json")

    # --- plugin.py ---
    if args.template == "advanced":
        plugin_py = (
            f'"""Advanced {name} plugin."""\n\n'
            f"from __future__ import annotations\n\n"
            f"from typing import Any\n\n\n"
            f"class {base_name}:\n"
            f'    """{name} plugin."""\n\n'
            f"    @property\n"
            f"    def name(self) -> str:\n"
            f'        return "{name}"\n\n'
            f"    @property\n"
            f"    def version(self) -> str:\n"
            f'        return "0.1.0"\n\n'
            f"    @property\n"
            f"    def description(self) -> str:\n"
            f'        return "{description}"\n\n'
            f"    def initialize(self, context: dict[str, Any]) -> None:\n"
            f'        """Called when plugin is loaded."""\n'
            f"        pass\n\n"
            f"    def shutdown(self) -> None:\n"
            f'        """Called when plugin is unloaded."""\n'
            f"        pass\n\n"
            f"    def register_commands(self, registry: Any) -> None:\n"
            f'        """Register CLI commands."""\n'
            f"        pass\n\n"
            f"    def register_hooks(self, registry: Any) -> None:\n"
            f'        """Register hooks."""\n'
            f'        registry.register_hook("post_execute", self.on_post_execute)\n\n'
            f"    def on_post_execute(self, result: Any) -> None:\n"
            f"        pass\n"
        )
    else:
        plugin_py = (
            f'"""{name} plugin."""\n\n\n'
            f"class {base_name}:\n"
            f"    @property\n"
            f"    def name(self):\n"
            f'        return "{name}"\n'
            f"\n"
            f"    @property\n"
            f"    def version(self):\n"
            f'        return "0.1.0"\n'
            f"\n"
            f"    @property\n"
            f"    def description(self):\n"
            f'        return "{description}"\n'
        )
    (plugin_dir / "plugin.py").write_text(plugin_py, encoding="utf-8")
    console.success(f"Created {name}/plugin.py")

    # Stamp the entry-point checksum now that plugin.py exists, so load() can
    # verify integrity instead of treating the plugin as unverified.
    from opencontext_core.plugin_system import stamp_plugin_integrity

    stamp_plugin_integrity(plugin_dir)

    readme = (
        f"# {name}\n\n"
        f"{description}\n\n"
        f"## Installation\n\n"
        f"```bash\nopencontext plugin install {name}\n```\n\n"
        f"## Usage\n\n"
        f"Describe how to use this plugin.\n"
    )
    (plugin_dir / "README.md").write_text(readme, encoding="utf-8")
    console.success(f"Created {name}/README.md")

    console.info(f"Plugin '{name}' scaffolded. Edit plugin.py to add your logic.")


def _plugin_install(args: Any) -> None:
    """Install a plugin."""

    if getattr(args, "marketplace", ""):
        _plugin_install_marketplace(args)
        return

    installer = PluginInstaller()

    if args.github:
        console.info(f"Installing from GitHub: {args.github}")
        result = installer.install_from_github(args.github, name=args.name)
    elif args.url:
        console.info(f"Installing from URL: {args.url}")
        result = installer.install_from_url(args.name, args.url)
    else:
        version = args.ver or None
        result = installer.install_from_registry(args.name, version=version)

    _print_install_result(result)


def _plugin_install_marketplace(args: Any) -> None:
    """Install a marketplace bundle with full PR-016 enforcement."""

    host = _host_config()
    if not getattr(host, "marketplace_enabled", False):
        err_console.error(
            "Marketplace install is disabled. Enable plugins.marketplace_enabled"
            " in opencontext.yaml to use multi-asset bundles."
        )
        return

    from opencontext_core.marketplace import MarketplaceInstaller

    installer = MarketplaceInstaller()
    result = installer.install(args.marketplace, verify_key=(args.key or None))

    if result.status == "installed":
        console.success(result.message)
    else:
        err_console.error(result.message)
    if result.trust_level:
        console.dim(f"   Trust:     {result.trust_level}")
    if result.signature_verified:
        console.dim("   Signature: verified")
    if result.receipt_path:
        console.dim(f"   Receipt:   {result.receipt_path}")
    for kind, ids in result.contributions:
        console.dim(f"   provides {kind}: {', '.join(ids)}")


def _plugin_publish(args: Any) -> None:
    """Build, leak-scan, validate, version, and sign a marketplace package."""

    from opencontext_core.marketplace import publish_package

    result = publish_package(
        args.src,
        key=(args.key or None),
        allow=getattr(args, "allow", False),
        out_dir=(args.out or None),
    )

    if result.ok:
        console.success(result.message)
        if result.archive_path:
            console.dim(f"   Archive: {result.archive_path}")
        console.dim(f"   Signed:  {'yes' if result.signed else 'no (no --key)'}")
        if result.findings:
            console.dim(
                f"   Note:    {len(result.findings)} secret finding(s) acknowledged (--allow)"
            )
    else:
        err_console.error(result.message or "publish failed")
        for err in result.errors:
            err_console.dim(f"   {err}")
        for finding in result.findings:
            # Fingerprint-only — never the raw secret value.
            err_console.dim(
                f"   leak: {finding.kind} fp={finding.fingerprint} {finding.redacted_value}"
            )


def _plugin_remove(args: Any) -> None:
    """Remove a plugin."""

    registry = PluginRegistry()

    info = registry.get_info(args.name)
    if info is None:
        err_console.error(f"Plugin '{args.name}' not found.")
        console.dim(f"Installed plugins: {', '.join(p.name for p in registry.discover())}")
        return

    console.info(f"Removing '{args.name}'...")

    plugin_dir = registry.plugins_dir / args.name
    backup_dir = plugin_dir.parent / f".{args.name}.bak"
    if plugin_dir.exists():
        import shutil

        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        shutil.copytree(plugin_dir, backup_dir)

    if registry.remove(args.name):
        if backup_dir.exists():
            import shutil

            shutil.rmtree(backup_dir)
        console.success(f"'{args.name}' removed.")
    else:
        if backup_dir.exists():
            import shutil

            plugin_dir.mkdir(parents=True, exist_ok=True)
            for item in backup_dir.iterdir():
                shutil.copy2(item, plugin_dir / item.name)
            shutil.rmtree(backup_dir)
        err_console.error(f"Failed to remove '{args.name}'.")


def _plugin_update(args: Any) -> None:
    """Check and apply plugin updates."""

    updater = PluginUpdater()

    if args.name:
        console.info(f"Checking updates for '{args.name}'...")
        result = updater.check_updates_for(args.name)
        _print_install_result(result)
        return

    console.info("Checking all plugins for updates...")
    results = updater.check_updates()

    updated = [r for r in results if r.status == "updated"]
    skipped = [r for r in results if r.status == "skipped"]
    failed = [r for r in results if r.status == "failed"]

    for r in results:
        if r.status == "updated":
            console.success(r.message)
        elif r.status == "failed":
            err_console.error(r.message)
        else:
            console.dim(r.message)

    console.print()
    if updated:
        console.success(f"{len(updated)} plugin(s) updated.")
    if skipped:
        console.dim(f"{len(skipped)} plugin(s) up to date.")
    if failed:
        err_console.error(f"{len(failed)} plugin(s) failed to update.")
        for r in failed:
            if r.error:
                err_console.dim(f"   {r.name}: {r.error}")
    if not updated and not failed:
        console.success("All plugins up to date.")


def _plugin_info(args: Any) -> None:
    """Show plugin details."""

    registry = PluginRegistry()
    info = registry.get_info(args.name)

    latest_version = "unknown"
    try:
        fetcher = RegistryFetcher()
        entry = fetcher.get(args.name)
        if entry and entry.versions:
            latest_version = entry.versions[0].version
    except Exception:
        pass

    if args.json:
        if info is None:
            data = {
                "name": args.name,
                "installed": False,
                "latest": latest_version,
            }
        else:
            data = {
                "name": info.name,
                "installed": True,
                "version": info.version,
                "latest": latest_version,
                "description": info.description,
                "author": info.author,
                "homepage": info.homepage,
                "repository": info.repository,
                "enabled": info.enabled,
                "install_source": info.install_source,
                "source_url": info.source_url,
                "entry_point": info.entry_point,
                "installed_at": info.installed_at,
                "updated_at": info.updated_at,
                "hooks": info.hooks,
            }
            if latest_version != "unknown" and latest_version != info.version:
                data["update_available"] = True
        print(json.dumps(data, indent=2))
        return

    if info is None:
        fetcher = RegistryFetcher()
        entry = fetcher.get(args.name)
        if entry:
            console.header(entry.name)
            console.print(f"  Description: {entry.description}")
            console.print(f"  Author:      {entry.author or '—'}")
            console.print(f"  Homepage:    {entry.homepage or '—'}")
            console.print(f"  Repository:  {entry.repository or '—'}")
            if entry.versions:
                console.print(f"  Versions:    {', '.join(v.version for v in entry.versions)}")
            console.info(f"Not installed. Install with: opencontext plugin install {args.name}")
            return
        err_console.error(f"Plugin '{args.name}' not found locally or in registry.")
        return

    console.header(info.name)
    console.print(f"  Version:      {info.version}")
    if latest_version != "unknown" and latest_version != info.version:
        console.print(f"  Latest:       {latest_version}  (update available)")
    else:
        console.print(f"  Latest:       {latest_version}")
    console.print(f"  Description:  {info.description}")
    console.print(f"  Author:       {info.author or '—'}")
    console.print(f"  Homepage:     {info.homepage or '—'}")
    console.print(f"  Repository:   {info.repository or '—'}")
    console.print(f"  Status:       {'enabled' if info.enabled else 'disabled'}")
    console.print(f"  Source:       {info.install_source}")
    console.print(f"  Source URL:   {info.source_url or '—'}")
    console.print(f"  Entry point:  {info.entry_point}")
    console.print(f"  Installed at: {info.installed_at or '—'}")
    console.print(f"  Updated at:   {info.updated_at or '—'}")
    # PR-016: surface marketplace trust/publisher + a compatibility marker.
    meta = _marketplace_meta(registry, args.name)
    if meta.get("trust_level"):
        console.print(f"  Trust:        {meta['trust_level']}")
    if meta.get("publisher"):
        console.print(f"  Publisher:    {meta['publisher']}")
    if info.incompatible:
        console.print(f"  Compat:       [bold]✗[/] {info.incompatible}")
    else:
        console.print("  Compat:       [green]✓[/] compatible")
    if info.hooks:
        console.print(f"  Hooks:        {', '.join(info.hooks)}")


def _marketplace_meta(registry: PluginRegistry, name: str) -> dict[str, str]:
    """Read marketplace metadata (trust/publisher) from an installed plugin.json."""
    manifest_path = registry.plugins_dir / name / "plugin.json"
    if not manifest_path.exists():
        return {}
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        "trust_level": str(raw.get("trust_level", "")),
        "publisher": str(raw.get("publisher", "")),
        "package_id": str(raw.get("package_id", "")),
    }


def _plugin_enable(args: Any) -> None:
    """Enable a plugin."""

    registry = PluginRegistry()
    if registry.enable(args.name):
        console.success(f"'{args.name}' enabled.")
    else:
        err_console.error(f"Plugin '{args.name}' not found.")


def _plugin_disable(args: Any) -> None:
    """Disable a plugin."""

    registry = PluginRegistry()
    if registry.disable(args.name):
        console.warning(f"'{args.name}' disabled.")
    else:
        err_console.error(f"Plugin '{args.name}' not found.")


def _host_config() -> Any:
    """Load the plugin host config, falling back to defaults (zero-config)."""
    try:
        from opencontext_core.config import load_config_or_defaults

        return load_config_or_defaults().plugins
    except Exception:
        from opencontext_core.config import PluginHostConfig

        return PluginHostConfig()


def _plugin_activate(args: Any) -> None:
    """Run a plugin through the full PR-015 lifecycle."""

    registry = PluginRegistry()
    if registry.get_info(args.name) is None:
        err_console.error(f"Plugin '{args.name}' not found.")
        return
    result = registry.activate(args.name, host_config=_host_config())

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "plugin": result.plugin,
                    "status": str(result.status),
                    "stage": str(result.stage),
                    "reason": result.reason,
                    "contributions": [
                        {"extension_point": c.extension_point, "id": c.contribution_id}
                        for c in result.contributions
                    ],
                },
                indent=2,
            )
        )
        return

    line = f"{result.plugin}: {result.status} (stage: {result.stage})"
    if result.active:
        console.success(line)
    else:
        err_console.error(line)
    if result.reason:
        console.dim(f"   {result.reason}")
    for c in result.contributions:
        console.dim(f"   contributes {c.extension_point}: {c.contribution_id}")


def _plugin_health(args: Any) -> None:
    """Activate a plugin and report its health-check verdict."""

    registry = PluginRegistry()
    if registry.get_info(args.name) is None:
        err_console.error(f"Plugin '{args.name}' not found.")
        return
    result = registry.activate(args.name, host_config=_host_config())
    healthy = result.active
    if healthy:
        console.success(f"{result.plugin}: healthy")
    else:
        err_console.error(f"{result.plugin}: {result.status}")
        err_console.dim(f"   {result.reason}  (stage: {result.stage})")


def _plugin_benchmark(args: Any) -> None:
    """Run the plugin's benchmark gate (declared suite before activation)."""

    registry = PluginRegistry()
    info = registry.get_info(args.name)
    if info is None:
        err_console.error(f"Plugin '{args.name}' not found.")
        return
    try:
        import json as _json
        from pathlib import Path

        from opencontext_core.plugins.benchmark_gate import benchmark_gate
        from opencontext_core.plugins.manifest import PluginManifest

        raw = _json.loads(
            (Path(registry.plugins_dir) / args.name / "plugin.json").read_text(encoding="utf-8")
        )
        manifest = PluginManifest.from_plugin_json(raw)
        host = _host_config()
        gate = benchmark_gate(
            manifest, enabled=getattr(host, "benchmark_on_install", True), runner=None
        )
    except Exception as exc:
        err_console.error(f"Benchmark gate error: {exc}")
        return

    state = "ran" if gate.ran else "skipped"
    line = f"{args.name}: benchmark {state} — {gate.reason}"
    if gate.passed:
        console.success(line)
    else:
        err_console.error(line)


def _print_install_result(result: Any) -> None:
    """Pretty-print an install result."""

    if result.status in ("installed", "updated"):
        console.success(result.message)
    elif result.status == "failed":
        err_console.error(result.message)
    else:
        console.dim(result.message)
    if result.source:
        console.dim(f"   Source: {result.source}")
    if result.error:
        err_console.dim(f"   Error:  {result.error}")
