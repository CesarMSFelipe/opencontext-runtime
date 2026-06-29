"""SDD model-profile CLI — manage per-phase model assignments.

Profiles map each SDD phase (explore, spec, design, apply, verify, ...) to a
model id, so a run can use cheap models for exploration and strong models where
it matters. Built-in profiles (default/cheap/hybrid/premium) ship ready; this
command lets you create custom profiles and override any single phase.
"""

from __future__ import annotations

import json
from typing import Any

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console
from opencontext_core.sdd_profiles import SDDProfileManager

SDD_PHASES = ("explore", "propose", "spec", "design", "tasks", "apply", "verify", "archive")


def add_profile_parser(subparsers: Any) -> None:
    """Add the ``profile`` command parser."""
    parser = subparsers.add_parser(
        "profile",
        help="Manage SDD model profiles (per-phase model assignment).",
        description=(
            "Manage per-phase SDD model profiles.\n\n"
            "  opencontext profile list                       List profiles\n"
            "  opencontext profile show hybrid                Show per-phase models\n"
            "  opencontext profile create mine --from hybrid  Create from a base\n"
            "  opencontext profile set mine apply gpt-5       Override one phase\n"
            "  opencontext profile delete mine                Delete a custom profile"
        ),
    )
    sub = parser.add_subparsers(dest="profile_command", required=True)

    list_p = sub.add_parser("list", help="List config profiles and per-phase model profiles.")
    list_p.add_argument("--json", action="store_true", help="Emit as JSON.")

    explain = sub.add_parser(
        "explain", help="Explain a profile (security/budget/approvals/observability)."
    )
    explain.add_argument("name")
    explain.add_argument("--json", action="store_true", help="Emit as JSON.")

    show = sub.add_parser("show", help="Show a profile's per-phase model assignments.")
    show.add_argument("name")
    show.add_argument("--json", action="store_true", help="Emit as JSON.")

    create = sub.add_parser("create", help="Create a profile.")
    create.add_argument("name")
    create.add_argument("--description", default="", help="Profile description.")
    create.add_argument(
        "--from", dest="base", default=None, help="Copy assignments from a profile."
    )

    set_p = sub.add_parser("set", help="Set the model for one phase of a profile.")
    set_p.add_argument("name")
    set_p.add_argument("phase", choices=SDD_PHASES)
    set_p.add_argument("model", help="Model id (e.g. anthropic/claude-opus-4 or 'default').")

    delete = sub.add_parser("delete", help="Delete a profile.")
    delete.add_argument("name")


def handle_profile(args: Any) -> int:
    """Dispatch a ``profile`` subcommand. Returns a process exit code."""
    manager = SDDProfileManager()
    command = args.profile_command

    if command == "list":
        return _list(manager, getattr(args, "json", False))
    if command == "explain":
        return _explain(args.name, getattr(args, "json", False))
    if command == "show":
        return _show(manager, args.name, getattr(args, "json", False))
    if command == "create":
        return _create(manager, args.name, args.description, args.base)
    if command == "set":
        return _set_phase(manager, args.name, args.phase, args.model)
    if command == "delete":
        return _delete(manager, args.name)
    return 1


def _list(manager: SDDProfileManager, as_json: bool = False) -> int:
    from opencontext_core import config_profiles

    # Config profiles (PR-013) — governance/routing posture.
    cfg = config_profiles.list_profiles()
    profiles = manager.list_profiles()
    if as_json:
        print(  # pure JSON to stdout
            json.dumps({"config_profiles": cfg, "model_profiles": profiles}, indent=2)
        )
        return 0

    console.header("Profiles")
    console.table(
        f"Config profiles ({len(cfg)})",
        ["Name", "Default", "Description"],
        [[p["name"], "✓" if p["default"] else "", p.get("description", "")] for p in cfg],
    )
    # Model profiles — per-phase model assignment family.
    console.table(
        f"Model profiles ({len(profiles)})",
        ["Name", "Description"],
        [[p["name"], p.get("description", "")] for p in profiles],
    )
    return 0


def _explain(name: str, as_json: bool) -> int:
    """Explain a profile's defaults via the shared explain logic."""
    from opencontext_core.explain import explain_profile

    info = explain_profile(name)
    if as_json:
        print(json.dumps(info, indent=2))
        return 0 if "error" not in info else 1
    if "error" in info:
        eprint(str(info["error"]))
        if info.get("next_action"):
            console.dim(f"  → {info['next_action']}")
        return 1
    console.header(f"Profile: {info['id']}")
    console.print(f"  family        : {info['family']}")
    if info.get("description"):
        console.print(f"  {info['description']}")
    if info["family"] == "config":
        console.print(f"  security      : {info['security']}")
        console.print(f"  policy        : {info['policy']}")
        console.print(f"  providers     : {info['providers']}")
        console.print(f"  approvals     : {info['approvals']}")
        console.print(f"  budget        : {info['budget']}")
        console.print(f"  observability : {info['observability']}")
    else:
        for phase, model in info.get("model_assignments", {}).items():
            console.print(f"  {phase:<10} {model}")
    return 0


def _show(manager: SDDProfileManager, name: str, as_json: bool) -> int:
    profile = manager.get_profile(name)
    if profile is None:
        eprint(f"Profile not found: {name}")
        return 1
    if as_json:
        print(json.dumps(profile.to_dict(), indent=2))
        return 0
    console.header(f"Profile: {name}")
    console.table(
        "Per-Phase Models",
        ["Phase", "Model"],
        [[phase, profile.model_assignments.get(phase, "default")] for phase in SDD_PHASES],
    )
    return 0


def _create(manager: SDDProfileManager, name: str, description: str, base: str | None) -> int:
    if name in manager.DEFAULT_PROFILES:
        eprint(f"'{name}' is a built-in profile.")
        console.dim(
            f"  Copy it under a new name: opencontext profile create my-{name} --from {name}"
        )
        return 1
    assignments: dict[str, str] = {}
    if base is not None:
        base_profile = manager.get_profile(base)
        if base_profile is None:
            eprint(f"Base profile not found: {base}")
            return 1
        assignments = dict(base_profile.model_assignments)
        if not description:
            description = f"Copied from {base}"
    manager.create_profile(name, description=description, model_assignments=assignments)
    console.success(f"Created profile {name}")
    return 0


def _set_phase(manager: SDDProfileManager, name: str, phase: str, model: str) -> int:
    if name in manager.DEFAULT_PROFILES:
        eprint(f"'{name}' is a built-in profile and can't be modified in place.")
        console.dim(f"  Copy it first: opencontext profile create my-{name} --from {name}")
        return 1
    profile = manager.get_profile(name)
    if profile is None:
        eprint(f"Profile not found: {name}. Create it first with 'profile create'.")
        return 1
    assignments = dict(profile.model_assignments)
    assignments[phase] = model
    manager.create_profile(name, description=profile.description, model_assignments=assignments)
    console.success(f"Set {name}.{phase} = {model}")
    return 0


def _delete(manager: SDDProfileManager, name: str) -> int:
    if name in manager.DEFAULT_PROFILES:
        eprint(f"Cannot delete the built-in profile: {name}")
        return 1
    if manager.delete_profile(name):
        console.success(f"Deleted profile {name}")
        return 0
    eprint(f"Profile not found: {name}")
    return 1
