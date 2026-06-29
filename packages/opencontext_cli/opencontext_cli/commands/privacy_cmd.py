"""Privacy rules management CLI commands.

Provides add-rule, list-rules, and remove-rule subcommands for managing
.opencontext/privacy.yaml in a human-friendly way.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console
from opencontext_core.harness.models import (
    AuditLevel,
    DataClassification,
    PermissionScope,
    PrivacyRule,
)


def add_privacy_parser(subparsers: Any) -> None:
    """Add privacy command parsers."""
    privacy_parser = subparsers.add_parser(
        "privacy",
        help="Manage privacy rules for the harness.",
        description=(
            "Manage privacy rules that restrict which providers and operations "
            "the harness can use during SDD phases. Rules are stored in "
            ".opencontext/privacy.yaml and activate when --privacy-profile "
            "is set to 'standard' or 'restricted'."
        ),
    )
    privacy_sub = privacy_parser.add_subparsers(dest="privacy_command", required=True)

    list_parser = privacy_sub.add_parser(
        "list",
        help="List all configured privacy rules.",
    )
    list_parser.add_argument("--json", action="store_true", help="Output as JSON.")

    add_parser = privacy_sub.add_parser(
        "add",
        help="Add a new privacy rule.",
        description=(
            "Add a privacy rule to .opencontext/privacy.yaml. "
            "The rule will be active when --privacy-profile is 'standard' or 'restricted'."
        ),
    )
    add_parser.add_argument("--name", required=True, help="Human-readable rule name.")
    add_parser.add_argument(
        "--scope",
        required=True,
        help=(
            "Comma-separated scopes: "
            "external_calls,file_read,file_write,secret_access,network_call."
        ),
    )
    add_parser.add_argument(
        "--classification",
        required=True,
        help="Minimum data classification: public,internal,sensitive,confidential.",
    )
    add_parser.add_argument(
        "--providers",
        default="",
        help="Comma-separated blocked provider names (empty = block all matching scopes).",
    )
    add_parser.add_argument(
        "--audit",
        default="basic",
        choices=["none", "basic", "detailed"],
        help="Audit level for this rule (default: basic).",
    )
    add_parser.add_argument(
        "--description",
        default="",
        help="Optional description explaining why this rule exists.",
    )
    add_parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt and add the rule directly.",
    )

    remove_parser = privacy_sub.add_parser(
        "remove",
        help="Remove a privacy rule by ID.",
    )
    remove_parser.add_argument(
        "rule_id",
        help="ID of the rule to remove (use 'opencontext privacy list' to see IDs).",
    )
    remove_parser.add_argument(
        "--force",
        action="store_true",
        help="Remove without confirmation prompt.",
    )


def handle_privacy(args: Any) -> None:
    """Handle privacy commands."""
    command = args.privacy_command

    if command == "list":
        _list_rules(args.json)
    elif command == "add":
        _add_rule(args)
    elif command == "remove":
        _remove_rule(args)
    else:
        eprint(f"Unknown privacy command: {command}")
        sys.exit(2)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _load_privacy_yaml(root: Path = Path(".")) -> tuple[dict[str, Any], Path]:
    """Load the privacy.yaml dict and return it with the path."""
    privacy_path = root / ".opencontext" / "privacy.yaml"
    if privacy_path.exists():
        data = yaml.unsafe_load(privacy_path.read_text(encoding="utf-8")) or {}
    else:
        data = {"privacy_rules": []}
    return data, privacy_path


def _save_privacy_yaml(data: dict[str, Any], privacy_path: Path) -> None:
    """Save the privacy.yaml dict."""
    privacy_path.parent.mkdir(parents=True, exist_ok=True)
    privacy_path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _list_rules(json_output: bool) -> None:
    """List all privacy rules."""
    data, _ = _load_privacy_yaml()
    rules_data = data.get("privacy_rules", [])

    if json_output:
        import json

        print(json.dumps(rules_data, indent=2))
        return

    console.header("Privacy Rules")
    if not rules_data:
        console.info("No privacy rules yet.")
        console.dim("Add one: opencontext privacy add --name ... --scope ...")
        return

    rows = []
    for r in rules_data:
        scopes = ", ".join(r.get("permission_scopes", []))
        classification = str(r.get("data_classification", "?"))
        audit = str(r.get("audit_level", "basic"))
        providers = r.get("provider_restrictions") or ["(all)"]
        rows.append(
            [
                r["id"],
                r.get("name", "?"),
                scopes,
                classification,
                ", ".join(str(p) for p in providers),
                audit,
            ]
        )
    console.table(
        "Privacy Rules",
        ["ID", "Name", "Scopes", "Classification", "Blocked Providers", "Audit"],
        rows,
    )
    console.dim(f"{len(rules_data)} rule(s) configured")


def _add_rule(args: Any) -> None:
    """Add a new privacy rule."""
    scope_strs = [s.strip() for s in args.scope.split(",")]
    try:
        scopes = [PermissionScope(s) for s in scope_strs]
    except ValueError:
        valid = [s.value for s in PermissionScope]
        eprint(f"Invalid scope(s): {args.scope}. Valid: {', '.join(valid)}")
        sys.exit(1)

    try:
        classification = DataClassification(args.classification)
    except ValueError:
        valid = [c.value for c in DataClassification]
        eprint(f"Invalid classification: {args.classification}. Valid: {', '.join(valid)}")
        sys.exit(1)

    try:
        audit_level = AuditLevel(args.audit)
    except ValueError:
        valid = [a.value for a in AuditLevel]
        eprint(f"Invalid audit level: {args.audit}. Valid: {', '.join(valid)}")
        sys.exit(1)

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]

    import uuid

    rule_id = f"rule-{uuid.uuid4().hex[:8]}"
    rule = PrivacyRule(
        id=rule_id,
        name=args.name,
        description=args.description or f"Rule: {args.name}",
        permission_scopes=scopes,
        data_classification=classification,
        provider_restrictions=providers,
        audit_level=audit_level,
    )

    data, privacy_path = _load_privacy_yaml()
    rules = data.get("privacy_rules", [])
    rules.append(rule.model_dump(mode="json"))
    data["privacy_rules"] = rules
    _save_privacy_yaml(data, privacy_path)

    console.success(f"Privacy rule added: {rule_id}")
    console.print(f"  Name: {args.name}")
    console.print(f"  Scopes: {args.scope}")
    console.print(f"  Classification: {args.classification}")
    console.print(f"  Providers blocked: {args.providers or '(all)'}")
    console.print(f"  Audit: {args.audit}")
    console.dim("Activate with: opencontext harness run --privacy-profile standard ...")


def _remove_rule(args: Any) -> None:
    """Remove a privacy rule by ID."""
    data, privacy_path = _load_privacy_yaml()
    rules = data.get("privacy_rules", [])
    rule_ids = [r["id"] for r in rules]

    if args.rule_id not in rule_ids:
        eprint(f"Rule not found: {args.rule_id}. Available: {', '.join(rule_ids) or '(none)'}")
        sys.exit(1)

    if not args.force:
        from opencontext_core import prompts

        if not prompts.confirm(f"Remove rule {args.rule_id}?", default=False):
            console.dim("Cancelled.")
            return

    data["privacy_rules"] = [r for r in rules if r["id"] != args.rule_id]
    _save_privacy_yaml(data, privacy_path)
    console.success(f"Removed: {args.rule_id}")
