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
    run_wizard,
    show_config,
)


def add_config_parser(subparsers: Any) -> None:
    """Add config command parsers."""

    config_parser = subparsers.add_parser(
        "config", help="Manage OpenContext configuration."
    )
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)

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
    reconf_parser = config_sub.add_parser(
        "reconfigure", help="Reconfigure a specific section."
    )
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

    command = args.config_command

    if command == "wizard":
        run_wizard(non_interactive=getattr(args, "non_interactive", False))
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


def _config_set(key: str, value: str) -> None:
    """Set a config value by key."""

    store = UserConfigStore()
    prefs = store.load()

    # Simple key-value mapping
    key_map: dict[str, tuple[str, type]] = {
        "security_mode": ("security_mode", str),
        "token_budget": ("default_token_budget", int),
        "max_input_tokens": ("max_input_tokens", int),
        "check_updates": ("check_updates", bool),
        "auto_optimize": ("learning_auto_optimize", bool),
    }

    if key in key_map:
        attr_name, attr_type = key_map[key]
        if attr_type == bool:
            parsed = value.lower() in ("true", "1", "yes", "on")
        elif attr_type == int:
            parsed = int(value)
        else:
            parsed = value
        setattr(prefs, attr_name, parsed)
        store.save(prefs)
        print(f"Set {key} = {parsed}")
    else:
        print(f"Unknown key: {key}")
        print(f"Available: {', '.join(key_map.keys())}")


def _config_get(key: str) -> None:
    """Get a config value by key."""

    store = UserConfigStore()
    prefs = store.load()

    key_map = {
        "security_mode": prefs.security_mode,
        "token_budget": prefs.default_token_budget,
        "max_input_tokens": prefs.max_input_tokens,
        "check_updates": prefs.check_updates,
        "auto_optimize": prefs.learning_auto_optimize,
        "first_run": prefs.first_run,
    }

    if key in key_map:
        print(f"{key} = {key_map[key]}")
    else:
        print(f"Unknown key: {key}")


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
    print(f"  {'─'*30} {'─'*25} {'─'*20} {'─'*20}")
    for b in backups:
        files_str = ", ".join(b.files) if b.files else "—"
        print(f"  {b.id:<30} {b.timestamp:<25} {b.description:<20} {files_str}")
    print(f"\n  {len(backups)} backup(s) available")
    print(f"\n  Restore: opencontext config restore <id>")


def _config_restore(backup_id: str) -> None:
    """Restore from a backup."""

    if ConfigBackupManager.restore_backup(backup_id):
        print(f"  ✓ Restored from backup: {backup_id}")
    else:
        print(f"  ✗ Backup not found: {backup_id}")
        print(f"    List available: opencontext config backups")
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

    # Rebuild index
    remaining = [b for b in backups if b.id not in
                  [r.id for r in ConfigBackupManager.list_backups()]]
    # Actually let's rebuild from disk
    from pathlib import Path
    index = []
    for entry_dir in sorted(ConfigBackupManager.BACKUP_DIR.iterdir()):
        if entry_dir.is_dir() and entry_dir.name.startswith("backup-"):
            try:
                ts = entry_dir.name.replace("backup-", "")
                desc = "auto-pre-change"  # rough default
                files = []
                for f in entry_dir.iterdir():
                    if f.is_file():
                        files.append(f.name)
                index.append({
                    "id": entry_dir.name,
                    "timestamp": ts,
                    "description": desc,
                    "files": files,
                })
            except OSError:
                continue

    ConfigBackupManager.INDEX_FILE.write_text(
        json.dumps(index, indent=2), encoding="utf-8"
    )

    print(f"  ✓ Removed {removed} backup(s) older than {keep_days} days")
    print(f"    {len(index)} backup(s) remaining")
