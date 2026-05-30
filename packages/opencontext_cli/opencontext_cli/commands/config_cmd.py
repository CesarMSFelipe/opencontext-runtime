"""Configuration management CLI commands.

Provides wizard, show, reset, reconfigure, backup,
restore, and cleanup subcommands for managing
OpenContext user preferences.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from opencontext_core.state import ConfigBackupManager
from opencontext_core.user_prefs import UserConfigStore
from opencontext_core.wizard import (
    reconfigure,
    reset_config,
    show_config,
)


def add_config_parser(subparsers: Any) -> None:
    """Add config command parsers."""

    config_parser = subparsers.add_parser("config", help="Manage OpenContext configuration.")
    config_sub = config_parser.add_subparsers(dest="config_command")

    # Wizard
    wizard_parser = config_sub.add_parser("wizard", help="Run configuration wizard.")
    wizard_parser.add_argument(
        "--non-interactive", action="store_true", help="Use defaults without prompts."
    )

    # Show
    config_sub.add_parser("show", help="Display current configuration.")

    # Reset
    config_sub.add_parser("reset", help="Reset to factory defaults.")

    # Reconfigure section
    reconf_parser = config_sub.add_parser("reconfigure", help="Reconfigure a specific section.")
    reconf_parser.add_argument(
        "section",
        choices=["security", "features", "tokens", "agents", "plugins"],
        help="Section to reconfigure.",
    )

    # Set individual values
    set_parser = config_sub.add_parser("set", help="Set a configuration value.")
    set_parser.add_argument("key", help="Configuration key (dot notation).")
    set_parser.add_argument("value", help="Value to set.")

    # Get individual values
    get_parser = config_sub.add_parser("get", help="Get a configuration value.")
    get_parser.add_argument("key", help="Configuration key (dot notation).")

    # Backup
    config_sub.add_parser("backup", help="Create a manual backup of configuration.")

    # List backups
    config_sub.add_parser("backups", help="List saved configuration backups.")

    # Restore
    restore_parser = config_sub.add_parser("restore", help="Restore configuration from a backup.")
    restore_parser.add_argument("id", help="Backup ID to restore.")

    # Cleanup old backups
    cleanup_parser = config_sub.add_parser("cleanup", help="Remove old backups.")
    cleanup_parser.add_argument(
        "--keep-days", type=int, default=30, help="Keep backups newer than this many days."
    )


def handle_config(args: Any) -> None:
    """Handle config commands."""

    command = getattr(args, "config_command", None)

    if command is None:
        # No subcommand — run the interactive wizard by default
        from opencontext_core.wizard import run_wizard, run_wizard_menu

        try:
            run_wizard_menu()
        except Exception:
            run_wizard(non_interactive=True)
        return

    if command == "wizard":
        use_tui = not getattr(args, "non_interactive", False)
        if use_tui:
            from opencontext_core.wizard import run_wizard_menu

            run_wizard_menu()
        else:
            from opencontext_core.wizard import run_wizard

            run_wizard(non_interactive=True)
    elif command == "show":
        show_config()
    elif command == "reset":
        reset_config()
    elif command == "reconfigure":
        reconfigure(args.section)
    elif command == "set":
        _config_set(args.key, args.value)
    elif command == "get":
        _config_get(args.key)
    elif command == "backup":
        _config_backup()
    elif command == "backups":
        _config_backups()
    elif command == "restore":
        _config_restore(args.id)
    elif command == "cleanup":
        _config_cleanup(args.keep_days)


# ── Dot-notation config paths ──────────────────────────────────────────────

# Schema of configurable paths: "path" -> (type, description)
CONFIG_PATHS: dict[str, tuple[type, str]] = {
    # Flat keys
    "security_mode": (str, "Security mode: private_project, enterprise, or air-gapped"),
    "default_token_budget": (int, "Default token budget per operation"),
    "max_input_tokens": (int, "Maximum input tokens"),
    "reserve_output_tokens": (int, "Reserved output tokens"),
    "check_updates": (bool, "Check for updates automatically"),
    "auto_optimize": (bool, "Auto-optimize token budgets based on usage"),
    "first_run": (bool, "Whether this is the first run"),
    "default_provider": (str, "Default LLM provider"),
    "default_model": (str, "Default LLM model"),
    # Nested: features.*
    "features.knowledge_graph": (bool, "Knowledge Graph (code indexing & search)"),
    "features.call_graph": (bool, "Call Graph (function call analysis)"),
    "features.learning_system": (bool, "Learning System (auto-optimize)"),
    "features.governance": (bool, "Governance (audit trails & policies)"),
    "features.mcp_server": (bool, "MCP Server (agent integration)"),
    "features.git_integration": (bool, "Git Integration"),
    "features.embeddings": (bool, "Embeddings (semantic search)"),
    "features.semantic_search": (bool, "Semantic Search"),
    # Nested: sdd.*
    "sdd.tdd_mode": (str, "TDD mode: ask, strict, or off"),
    "sdd.sdd_model_profile": (str, "SDD model profile: default, cheap, hybrid, premium"),
    "sdd.orchestrator_profile": (
        str,
        "Orchestrator profile: solo-compact, multi-phase, subagent-native",
    ),
    # Nested: agents.*
    "agents.default_client": (str, "Default agent client"),
    "agents.active_clients": (list, "Active agent clients (comma-separated)"),
}


def _resolve_config_path(prefs: Any, dotted: str) -> tuple[Any, str] | None:
    """Resolve a dotted path to (parent_object, attr_name) or None if invalid.

    Example: "features.knowledge_graph" -> (prefs.features, "knowledge_graph")
    """
    parts = dotted.split(".")
    obj = prefs
    for _i, part in enumerate(parts[:-1]):
        if hasattr(obj, part):
            obj = getattr(obj, part)
        else:
            return None
    return (obj, parts[-1])


def _get_all_config_paths() -> list[str]:
    """Return all available config paths sorted."""
    return sorted(CONFIG_PATHS.keys())


def _coerce_value(value: str, target_type: type) -> object:
    """Coerce a string value to the target type."""
    if target_type is bool:
        return value.lower() in ("true", "1", "yes", "on")
    elif target_type is int:
        return int(value)
    elif target_type is list:
        import json

        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        # Fallback: comma-separated
        return [item.strip() for item in value.split(",") if item.strip()]
    else:
        return value


def _config_set(key: str, value: str) -> None:
    """Set a config value using dot notation."""

    store = UserConfigStore()
    prefs = store.load()

    if key in CONFIG_PATHS:
        _target_type, _description = CONFIG_PATHS[key]
        resolved = _resolve_config_path(prefs, key)
        if resolved is None:
            print(f"Error: Cannot resolve path '{key}'")
            return
        parent, attr = resolved
        try:
            parsed = _coerce_value(value, _target_type)
            setattr(parent, attr, parsed)
            store.save(prefs)
            print(f"Set {key} = {parsed}")
        except (ValueError, TypeError) as exc:
            print(f"Error: Cannot set '{key}' to '{value}': {exc}")
            print(f"Expected type: {_target_type.__name__}")
    else:
        print(f"Unknown key: {key}")
        print(f"Available paths ({len(CONFIG_PATHS)}):")
        for path, (typ, desc) in sorted(CONFIG_PATHS.items()):
            print(f"  {path}  ({typ.__name__})  {desc}")


def _config_get(key: str) -> None:
    """Get a config value by dot-notation key."""

    store = UserConfigStore()
    prefs = store.load()

    if key in CONFIG_PATHS:
        _target_type, _description = CONFIG_PATHS[key]
        resolved = _resolve_config_path(prefs, key)
        if resolved is None:
            print(f"Error: Cannot resolve path '{key}'")
            return
        parent, attr = resolved
        value = getattr(parent, attr, "<not set>")
        print(f"{key} = {value}")
    else:
        print(f"Unknown key: {key}")
        # Suggest the closest key (replace dots with underscores for display)
        candidates = sorted(CONFIG_PATHS.keys())
        key_norm = key.lower().replace(".", "_")
        suggestions = [c for c in candidates if key_norm in c.lower() or c.lower() in key_norm]
        if suggestions:
            print(f"Hint: did you mean {suggestions[0]!r}?")
        print(f"Available paths ({len(CONFIG_PATHS)}):")
        for path, (typ, desc) in sorted(CONFIG_PATHS.items()):
            print(f"  {path}  ({typ.__name__})  {desc}")


def _config_backup() -> None:
    """Create a manual backup."""

    backup_id = ConfigBackupManager.create_backup(description="manual")
    print(f"  ✓ Backup created: {backup_id}")
    print(f"    Location: {ConfigBackupManager.BACKUP_DIR / backup_id}")


def _config_backups() -> None:
    """List backups."""

    backups = ConfigBackupManager.list_backups()
    if not backups:
        print("  No backups found.")
        print(f"  Backup directory: {ConfigBackupManager.BACKUP_DIR}")
        return

    print()
    print(f"  {'Backup ID':<30} {'Timestamp':<25} {'Description':<20} {'Files'}")
    print(f"  {'─' * 30} {'─' * 25} {'─' * 20} {'─' * 20}")
    for b in backups:
        files_str = ", ".join(b.files) if b.files else "—"
        print(f"  {b.id:<30} {b.timestamp:<25} {b.description:<20} {files_str}")
    print(f"\n  {len(backups)} backup(s) available")
    print("\n  Restore: opencontext config restore <id>")


def _config_restore(backup_id: str) -> None:
    """Restore from a backup."""

    if ConfigBackupManager.restore_backup(backup_id):
        print(f"  ✓ Restored from backup: {backup_id}")
    else:
        print(f"  ✗ Backup not found: {backup_id}")
        print("    List available: opencontext config backups")
        sys.exit(1)


def _config_cleanup(keep_days: int) -> None:
    """Clean up old backups beyond keep_days."""

    from datetime import datetime, timedelta

    backups = ConfigBackupManager.list_backups()
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = 0

    for b in backups:
        try:
            ts = datetime.strptime(b.timestamp, "%Y%m%dT%H%M%S")
            if ts < cutoff:
                backup_dir = ConfigBackupManager.BACKUP_DIR / b.id
                if backup_dir.exists():
                    import shutil

                    shutil.rmtree(backup_dir)
                removed += 1
        except (ValueError, OSError):
            continue

    # Rebuild index from disk — removes stale index entries for deleted dirs
    index = []
    for entry_dir in sorted(ConfigBackupManager.BACKUP_DIR.iterdir()):
        if entry_dir.is_dir() and entry_dir.name.startswith("backup-"):
            try:
                ts_str = entry_dir.name.replace("backup-", "")
                desc = "auto-pre-change"
                files = sorted(f.name for f in entry_dir.iterdir() if f.is_file())
                index.append(
                    {
                        "id": entry_dir.name,
                        "timestamp": ts_str,
                        "description": desc,
                        "files": files,
                    }
                )
            except OSError:
                continue

    ConfigBackupManager.INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")

    print(f"  ✓ Removed {removed} backup(s) older than {keep_days} days")
    print(f"    {len(index)} backup(s) remaining")
