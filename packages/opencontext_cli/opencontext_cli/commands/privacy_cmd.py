"""Privacy rules management CLI commands.

Provides add-rule, list-rules, and remove-rule subcommands for managing
.opencontext/privacy.yaml in a human-friendly way.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

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
        console.print(f"[red]Unknown privacy command: {command}[/]")


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

    if not rules_data:
        console.print("[dim]No privacy rules configured.[/]")
        console.print("[dim]Run 'opencontext privacy add --name ... --scope ...' to add one.[/]")
        return

    if json_output:
        import json

        console.print(json.dumps(rules_data, indent=2))
        return

    console.print(f"\n[bold]Privacy Rules ({len(rules_data)})[/]\n")
    for r in rules_data:
        scopes = ", ".join(r.get("permission_scopes", []))
        classification = r.get("data_classification", "?")
        audit = r.get("audit_level", "basic")
        providers = r.get("provider_restrictions") or ["(all)"]
        console.print(f"  [cyan]{r['id']}[/]  {r.get('name', '?')}")
        console.print(f"          Scopes: {scopes}")
        console.print(f"          Classification: {classification}")
        console.print(f"          Blocked providers: {', '.join(str(p) for p in providers)}")
        console.print(f"          Audit: {audit}")
        if r.get("description"):
            console.print(f"          {r['description']}")
        console.print()


def _add_rule(args: Any) -> None:
    """Add a new privacy rule."""
    scope_strs = [s.strip() for s in args.scope.split(",")]
    try:
        scopes = [PermissionScope(s) for s in scope_strs]
    except ValueError:
        valid = [s.value for s in PermissionScope]
        console.print(f"[red]Invalid scope(s): {args.scope}[/]")
        console.print(f"  Valid: {', '.join(valid)}")
        return

    try:
        classification = DataClassification(args.classification)
    except ValueError:
        valid = [c.value for c in DataClassification]
        console.print(f"[red]Invalid classification: {args.classification}[/]")
        console.print(f"  Valid: {', '.join(valid)}")
        return

    try:
        audit_level = AuditLevel(args.audit)
    except ValueError:
        valid = [a.value for a in AuditLevel]
        console.print(f"[red]Invalid audit level: {args.audit}[/]")
        console.print(f"  Valid: {', '.join(valid)}")
        return

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

    console.print(f"[green]✓[/] Privacy rule added: [cyan]{rule_id}[/]")
    console.print(f"  Name: {args.name}")
    console.print(f"  Scopes: {args.scope}")
    console.print(f"  Classification: {args.classification}")
    console.print(f"  Providers blocked: {args.providers or '(all)'}")
    console.print(f"  Audit: {args.audit}")
    console.print()
    console.print("[dim]Activate with: opencontext harness run --privacy-profile standard ...[/]")


def _remove_rule(args: Any) -> None:
    """Remove a privacy rule by ID."""
    data, privacy_path = _load_privacy_yaml()
    rules = data.get("privacy_rules", [])
    rule_ids = [r["id"] for r in rules]

    if args.rule_id not in rule_ids:
        console.print(f"[red]Rule not found: {args.rule_id}[/]")
        console.print(f"  Available: {', '.join(rule_ids) or '(none)'}")
        return

    if not args.force:
        from opencontext_core import prompts

        if not prompts.confirm(f"Remove rule {args.rule_id}?", default=False):
            console.print("[dim]Cancelled.[/]")
            return

    data["privacy_rules"] = [r for r in rules if r["id"] != args.rule_id]
    _save_privacy_yaml(data, privacy_path)
    console.print(f"[green]✓[/] Removed: [cyan]{args.rule_id}[/]")
