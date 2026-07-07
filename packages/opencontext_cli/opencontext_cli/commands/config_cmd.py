"""Configuration management CLI commands.

Provides wizard, show, reset, reconfigure, backup,
restore, and cleanup subcommands for managing
OpenContext user preferences.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from opencontext_core.dx.console_styles import BrandConsole, console
from opencontext_core.state import ConfigBackupManager
from opencontext_core.user_prefs import UserConfigStore
from opencontext_core.wizard import (
    reconfigure,
    reset_config,
    show_config,
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


def _interface_settings(root: Path | None = None) -> Any:
    """Effective ``interface`` settings for CLI gating (CFG-004; fail-open defaults)."""
    from opencontext_core.config_resolver import resolve_interface

    return resolve_interface(root if root is not None else Path.cwd())


def add_config_parser(subparsers: Any) -> None:
    """Add config command parsers."""

    config_parser = subparsers.add_parser("config", help="Manage OpenContext configuration.")
    config_sub = config_parser.add_subparsers(dest="config_command")

    wizard_parser = config_sub.add_parser("wizard", help="Run configuration wizard.")
    wizard_parser.add_argument(
        "--non-interactive", action="store_true", help="Use defaults without prompts."
    )

    show_p = config_sub.add_parser("show", help="Display current configuration.")
    show_p.add_argument(
        "--root",
        default=None,
        help="Project root for resolving opencontext.yaml (default: cwd).",
    )
    show_p.add_argument("--json", action="store_true", help="Emit JSON (CI-friendly).")

    # Explain — effective config with per-key source layer/file/line (plan §6).
    explain_p = config_sub.add_parser(
        "explain",
        help="Explain the effective config: value, source layer, file and line per key.",
    )
    explain_p.add_argument(
        "--root",
        default=None,
        help="Project root for resolving opencontext.yaml (default: cwd).",
    )
    explain_p.add_argument("--json", action="store_true", help="Emit JSON (CI-friendly).")
    # Runtime CLI-flag layer (plan §6 layer 7, CFG-003): these feed the layered
    # resolver's `cli_overrides` and therefore beat OPENCONTEXT_* env vars.
    from opencontext_core.config_profiles import profile_names

    explain_p.add_argument(
        "--profile",
        choices=profile_names(),
        default=None,
        help="Override the active configuration profile for this invocation (beats env).",
    )
    explain_p.add_argument(
        "--set",
        dest="set_overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override a dotted config key for this invocation (beats env; repeatable).",
    )
    # Temporary run-override layer (plan §6 layer 8): beats CLI flags.
    explain_p.add_argument(
        "--run-override",
        dest="run_overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Temporary run override for a dotted config key (beats --set/--profile).",
    )

    config_sub.add_parser("reset", help="Reset to factory defaults.")

    reconf_parser = config_sub.add_parser("reconfigure", help="Reconfigure a specific section.")
    reconf_parser.add_argument(
        "section",
        choices=["security", "features", "tokens", "agents", "plugins"],
        help="Section to reconfigure.",
    )

    set_parser = config_sub.add_parser("set", help="Set a configuration value.")
    set_parser.add_argument("key", help="Configuration key (dot notation).")
    set_parser.add_argument("value", help="Value to set.")

    # Get individual values
    get_parser = config_sub.add_parser("get", help="Get a configuration value.")
    get_parser.add_argument("key", help="Configuration key (dot notation).")

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

    # Doctor — validate the project's opencontext.yaml (PR-013, SPEC-CLI-013-05).
    doctor_parser = config_sub.add_parser(
        "doctor", help="Validate opencontext.yaml (schema/keys/profile/providers/refs)."
    )
    doctor_parser.add_argument("--root", default=".", help="Project root.")
    doctor_parser.add_argument("--json", action="store_true", help="JSON output.")
    doctor_parser.add_argument(
        "--strict", action="store_true", help="Exit non-zero if any check fails."
    )

    from opencontext_cli.commands.migration_cmd import add_migrate_subparser

    add_migrate_subparser(config_sub, "config")


def handle_config(args: Any) -> None:
    """Handle config commands."""

    command = getattr(args, "config_command", None)

    if command == "migrate":
        from opencontext_cli.commands.migration_cmd import handle_migrate

        raise SystemExit(handle_migrate("config", args))

    if command is None:
        # No subcommand — open the single configuration menu by default.
        # CFG-004: under a non-interactive profile (ci/agent posture) the
        # interactive menu is suppressed and the non-interactive wizard runs.
        from opencontext_cli.commands.menu_cmd import run_config_menu
        from opencontext_core.wizard import run_wizard

        if not _interface_settings().interactive:
            run_wizard(non_interactive=True)
            return
        try:
            run_config_menu()
        except Exception:
            run_wizard(non_interactive=True)
        return

    if command == "wizard":
        # CFG-004: the ci profile disables interactivity — the interactive
        # menu never launches; the wizard falls back to non-interactive.
        use_tui = not getattr(args, "non_interactive", False) and _interface_settings().interactive
        if use_tui:
            from opencontext_cli.commands.menu_cmd import run_config_menu

            run_config_menu()
        else:
            from opencontext_core.wizard import run_wizard

            run_wizard(non_interactive=True)
    elif command == "show":
        from pathlib import Path

        root = Path(getattr(args, "root", None) or ".").resolve()
        _require_parseable_project_yaml(root / "opencontext.yaml")
        # CFG-004: interface.json_default (ci profile) makes JSON the default
        # output; an explicit --json keeps working unchanged.
        if getattr(args, "json", False) or _interface_settings(root).json_default:
            _config_show_json(root=root)
        else:
            show_config(root=root)
    elif command == "explain":
        _config_explain(args)
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
    elif command == "doctor":
        _config_doctor(args)


def _config_show_json(root: Path | None = None) -> None:
    """Emit a machine-readable snapshot of current configuration.

    Schema: ``{schema, security_mode, data_classification, features,
    token_budgets, agents, plugins, project}``.
    Human-readable text goes to stderr/console only; stdout is the JSON object.
    """
    store = UserConfigStore()
    prefs = store.load()

    # Plugins
    plugins_list: list[dict[str, Any]] = []
    try:
        from opencontext_core.plugin_system import PluginRegistry

        for p in PluginRegistry().discover():
            plugins_list.append(
                {
                    "name": p.name,
                    "version": p.version,
                    "enabled": p.enabled,
                    "source": p.install_source,
                }
            )
    except Exception:
        pass

    # Project (opencontext.yaml) section
    project_root = Path(root) if root is not None else Path.cwd()
    yaml_path = project_root / "opencontext.yaml"
    project_info: dict[str, Any] = {"path": str(yaml_path), "exists": yaml_path.is_file()}
    if yaml_path.is_file():
        try:
            import yaml as _yaml

            _loaded = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            raw: dict[str, Any] = _loaded or {}
            memory_cfg = raw.get("memory", {}) or {}
            storage_cfg = raw.get("storage", {}) or {}
            sdd_cfg = raw.get("sdd", {}) or {}
            models_cfg = raw.get("models", {}) or {}
            project_info.update(
                {
                    "memory_provider": memory_cfg.get("provider"),
                    "storage_mode": storage_cfg.get("mode"),
                    "sdd_flow_mode": sdd_cfg.get("flow_mode"),
                    "models_roles": models_cfg.get("roles"),
                }
            )
        except Exception as exc:
            project_info["error"] = str(exc)

    payload: dict[str, Any] = {
        "schema": "opencontext/config-show/v1",
        "security_mode": prefs.security_mode,
        "data_classification": prefs.data_classification,
        "features": dict(vars(prefs.features)),
        "token_budgets": {
            "default": prefs.default_token_budget,
            "max_input": prefs.max_input_tokens,
        },
        "agents": prefs.agent_integrations,
        "plugins": plugins_list,
        "project": project_info,
        "error": None,
    }
    print(json.dumps(payload, indent=2, default=str))


def _require_parseable_project_yaml(yaml_path: Path) -> None:
    """Raise the CONFIG_INVALID contract error when *yaml_path* is unparseable.

    Missing files are fine (zero-config defaults); a file that exists but does
    not parse must fail with the structured envelope, exit code 3 (GAP-024).
    """
    if not yaml_path.is_file():
        return
    import yaml as _yaml

    from opencontext_cli.contracts import CliContractError

    try:
        _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except _yaml.YAMLError as exc:
        raise CliContractError(
            "CONFIG_INVALID",
            f"Invalid YAML in {yaml_path}: {exc}",
            hint=(
                "Fix the YAML syntax in opencontext.yaml, restore a backup with "
                "'opencontext config restore', or re-create it with 'opencontext init'."
            ),
            status="needs_configuration",
        ) from exc


def _parse_kv_overrides(pairs: list[str], flag: str) -> dict[str, Any]:
    """Parse repeatable ``KEY=VALUE`` pairs into a nested override mapping.

    Keys use dot notation (``interface.json_default``); values are YAML-parsed
    so ``true``/``2`` arrive typed. A pair without ``=`` fails with the
    CONFIG_INVALID contract envelope naming the offending flag.
    """
    import yaml as _yaml

    from opencontext_cli.contracts import CliContractError

    out: dict[str, Any] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            raise CliContractError(
                "CONFIG_INVALID",
                f"Invalid {flag} value: {pair!r} (expected KEY=VALUE).",
                hint=f"Use dotted keys, e.g. {flag} ui_language=en",
                status="needs_configuration",
            )
        try:
            parsed = _yaml.safe_load(value)
        except _yaml.YAMLError:
            parsed = value
        node = out
        parts = key.strip().split(".")
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = parsed
    return out


def _config_explain(args: Any) -> None:
    """Explain the effective config: value + source layer/file/line per key."""
    from opencontext_cli.contracts import CliContractError
    from opencontext_core.config_explain import explain, redact_secret_input_values
    from opencontext_core.errors import ConfigurationError

    root = Path(getattr(args, "root", None) or ".").resolve()
    # CFG-003 / plan §6 layers 7-8: real CLI flags feed the resolver's override
    # layers, so a flag beats an OPENCONTEXT_* env var end-to-end.
    cli_overrides = _parse_kv_overrides(list(getattr(args, "set_overrides", []) or []), "--set")
    if getattr(args, "profile", None):
        cli_overrides["profile"] = args.profile
    run_overrides = _parse_kv_overrides(
        list(getattr(args, "run_overrides", []) or []), "--run-override"
    )
    try:
        payload = explain(root, cli_overrides=cli_overrides, run_overrides=run_overrides)
    except ConfigurationError as exc:
        # Never echo secret-shaped config values in the envelope (JSON stdout)
        # or the human stderr path — both render this message.
        raise CliContractError(
            "CONFIG_INVALID",
            redact_secret_input_values(str(exc)),
            hint=(
                "Fix opencontext.yaml (run 'opencontext config doctor' for the "
                "failing keys), or pass --config <path> to use another file."
            ),
            status="needs_configuration",
        ) from exc

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return

    console.header("Config Explain")
    console.print(f"  Profile: {payload['profile']}")
    console.print(f"  Validation: {payload['validation']['status']}")
    non_default = {
        key: entry for key, entry in payload["sources"].items() if entry["source"] != "defaults"
    }
    if non_default:
        console.table(
            "Overridden keys",
            ["Key", "Value", "Source", "Location"],
            [
                [
                    key,
                    str(entry["value"]),
                    entry["source"],
                    f"{entry['path']}:{entry['line']}" if entry["path"] else "—",
                ]
                for key, entry in sorted(non_default.items())
            ],
        )
    else:
        console.dim("  All keys at built-in defaults.")
    for conflict in payload["conflicts"]:
        console.warning(
            f"  conflict: {conflict['key']} won by '{conflict['winner']}' "
            f"over {', '.join(conflict['losers'])}"
        )
    for entry in payload["deprecated_keys"]:
        console.warning(f"  deprecated: {entry['key']} → {entry['hint']}")
    for key in payload["unknown_keys"]:
        console.warning(f"  unknown key: {key}")


def _config_doctor(args: Any) -> None:
    """Validate the project's opencontext.yaml and report each finding."""
    import json as _json

    from opencontext_core.config import find_config
    from opencontext_core.config_doctor import validate

    doctor_root = Path(getattr(args, "root", "."))
    doctor_file = doctor_root / "opencontext.yaml"
    if not doctor_file.exists():
        doctor_file = find_config(doctor_root) or doctor_file
    _require_parseable_project_yaml(doctor_file)

    diags = validate(getattr(args, "root", "."))
    failed = sum(1 for d in diags if d.status in ("failed", "error"))

    if getattr(args, "json", False):
        print(
            _json.dumps(
                {
                    "ok": failed == 0,
                    "failed": failed,
                    "deprecated_keys": [
                        d.name.removeprefix("config.deprecated_key.")
                        for d in diags
                        if d.name.startswith("config.deprecated_key.")
                    ],
                    "findings": [
                        {
                            "name": d.name,
                            "status": d.status,
                            "message": d.message,
                            "details": d.details,
                            "recommendation": d.recommendation,
                        }
                        for d in diags
                    ],
                },
                indent=2,
            )
        )
    else:
        console.header("Config Doctor")
        for d in diags:
            line = f"[{d.status}] {d.name}: {d.message}"
            if d.status == "passed":
                console.success(line)
            elif d.status == "warning":
                console.warning(line)
            elif d.status in ("failed", "error"):
                err_console.error(line)
            else:
                console.dim(line)
            if d.recommendation:
                console.dim(f"      → {d.recommendation}")
        console.print(f"\n  {len(diags)} check(s), {failed} failed.")

    # A failing check means the config is unhealthy: exit non-zero so `config
    # doctor` gates the same way `verify`/`status` do (previously it exited 0 even
    # with ok:false, so scripts/CI could not detect a bad config).
    if failed:
        sys.exit(1)


# ── Dot-notation config paths ──────────────────────────────────────────────

# Key prefixes that belong to opencontext.yaml rather than user-prefs.
# Keys under these prefixes that are not in CONFIG_PATHS should direct the user
# to edit opencontext.yaml directly (or use a future `config yaml set` command).
_YAML_SECTION_PREFIXES: tuple[str, ...] = (
    "runtime.",
    "memory.",
    "storage.",
    "sdd.",
    "context.",
    "models.",
    "security.",
)


def _is_yaml_section_key(key: str) -> bool:
    """Return True when *key* starts with a known opencontext.yaml section prefix."""
    return any(key.startswith(prefix) for prefix in _YAML_SECTION_PREFIXES)


# Schema of configurable paths: "path" -> (type, description)
CONFIG_PATHS: dict[str, tuple[type, str]] = {
    # Flat keys
    "security_mode": (str, "Security mode: developer, private_project, enterprise, or air_gapped"),
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


def _bridge_to_project_yaml(key: str, value: object) -> None:
    """Mirror a runtime-affecting pref into the project's opencontext.yaml.

    The runtime reads opencontext.yaml, not user-prefs, so without this a
    `config set` of e.g. embeddings would never take effect. Validated +
    revert-on-failure logic lives in core ``config_sync``.
    """
    from opencontext_core.config_sync import RUNTIME_PREF_TO_YAML, sync_pref_to_yaml

    if key not in RUNTIME_PREF_TO_YAML:
        # Be honest: this key lives in user preferences and is not mirrored to the
        # opencontext.yaml the runtime reads, so it does not change runtime behavior.
        console.dim("  → saved to user preferences only (does not change runtime behavior)")
        return
    if sync_pref_to_yaml(key, value):
        console.dim(f"  → applied to opencontext.yaml ({RUNTIME_PREF_TO_YAML[key]})")


def _config_set(key: str, value: str) -> None:
    """Set a config value using dot notation."""

    store = UserConfigStore()
    prefs = store.load()

    if key in CONFIG_PATHS:
        _target_type, _description = CONFIG_PATHS[key]
        resolved = _resolve_config_path(prefs, key)
        if resolved is None:
            err_console.error(f"Cannot resolve path '{key}'")
            return
        parent, attr = resolved
        try:
            parsed = _coerce_value(value, _target_type)
            setattr(parent, attr, parsed)
            store.save(prefs)
            console.success(f"Set {key} = {parsed}")
            _bridge_to_project_yaml(key, parsed)
        except (ValueError, TypeError) as exc:
            err_console.error(f"Cannot set '{key}' to '{value}': {exc}")
            err_console.dim(f"Expected type: {_target_type.__name__}")
    elif _is_yaml_section_key(key):
        err_console.error(f"'{key}' is not a user-preference key.")
        err_console.error(
            "This key lives in opencontext.yaml — edit that file directly "
            "or use 'opencontext config wizard' to change it."
        )
        err_console.dim("  Location: opencontext.yaml in your project root")
        err_console.dim("  Future: `opencontext config yaml set <key> <value>` (coming soon)")
        sys.exit(1)
    else:
        err_console.error(f"Unknown key: {key}")
        console.dim(f"Available paths ({len(CONFIG_PATHS)}):")
        for path, (typ, desc) in sorted(CONFIG_PATHS.items()):
            console.dim(f"  {path}  ({typ.__name__})  {desc}")


def _config_get(key: str) -> None:
    """Get a config value by dot-notation key."""

    store = UserConfigStore()
    prefs = store.load()

    if key in CONFIG_PATHS:
        _target_type, _description = CONFIG_PATHS[key]
        resolved = _resolve_config_path(prefs, key)
        if resolved is None:
            err_console.error(f"Cannot resolve path '{key}'")
            return
        parent, attr = resolved
        value = getattr(parent, attr, "<not set>")
        console.print(f"{key} = {value}")
    elif _is_yaml_section_key(key):
        err_console.error(f"'{key}' is not a user-preference key.")
        err_console.error(
            "This key lives in opencontext.yaml — read it with 'opencontext config show' "
            "or edit the file directly."
        )
        err_console.dim("  Location: opencontext.yaml in your project root")
        sys.exit(1)
    else:
        err_console.error(f"Unknown key: {key}")
        # Suggest the closest key (replace dots with underscores for display)
        candidates = sorted(CONFIG_PATHS.keys())
        key_norm = key.lower().replace(".", "_")
        suggestions = [c for c in candidates if key_norm in c.lower() or c.lower() in key_norm]
        if suggestions:
            console.info(f"Hint: did you mean {suggestions[0]!r}?")
        console.dim(f"Available paths ({len(CONFIG_PATHS)}):")
        for path, (typ, desc) in sorted(CONFIG_PATHS.items()):
            console.dim(f"  {path}  ({typ.__name__})  {desc}")


def _config_backup() -> None:
    """Create a manual backup."""

    backup_id = ConfigBackupManager.create_backup(description="manual")
    console.success(f"Backup created: {backup_id}")
    console.dim(f"   Location: {ConfigBackupManager.BACKUP_DIR / backup_id}")


def _config_backups() -> None:
    """List backups."""

    backups = ConfigBackupManager.list_backups()
    console.header("Configuration Backups")
    if not backups:
        console.info("No backups yet.")
        console.dim(f"Backup directory: {ConfigBackupManager.BACKUP_DIR}")
        return

    console.table(
        "Backups",
        ["Backup ID", "Timestamp", "Description", "Files"],
        [
            [b.id, b.timestamp, b.description, ", ".join(b.files) if b.files else "—"]
            for b in backups
        ],
    )
    console.dim(f"{len(backups)} backup(s) available")
    console.dim("Restore: opencontext config restore <id>")


def _config_restore(backup_id: str) -> None:
    """Restore from a backup."""

    if ConfigBackupManager.restore_backup(backup_id):
        console.success(f"Restored from backup: {backup_id}")
    else:
        err_console.error(f"Backup not found: {backup_id}")
        err_console.dim("   List available: opencontext config backups")
        sys.exit(1)


def _config_cleanup(keep_days: int) -> None:
    """Clean up old backups beyond keep_days."""

    removed, remaining = ConfigBackupManager.cleanup(keep_days)
    console.success(f"Removed {removed} backup(s) older than {keep_days} days")
    console.dim(f"   {remaining} backup(s) remaining")
