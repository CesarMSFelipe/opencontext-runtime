"""SDD model-profile CLI — manage per-phase model assignments.

Profiles map each SDD phase (explore, spec, design, apply, verify, ...) to a
model id, so a run can use cheap models for exploration and strong models where
it matters. Built-in profiles (default/cheap/hybrid/premium) ship ready; this
command lets you create custom profiles and override any single phase.
"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table

from opencontext_core.sdd_profiles import SDDProfileManager

console = Console()

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

    sub.add_parser("list", help="List available profiles.")

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
        return _list(manager)
    if command == "show":
        return _show(manager, args.name, getattr(args, "json", False))
    if command == "create":
        return _create(manager, args.name, args.description, args.base)
    if command == "set":
        return _set_phase(manager, args.name, args.phase, args.model)
    if command == "delete":
        return _delete(manager, args.name)
    return 1


def _list(manager: SDDProfileManager) -> int:
    profiles = manager.list_profiles()
    table = Table(title=f"SDD profiles ({len(profiles)})")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    for p in profiles:
        table.add_row(p["name"], p.get("description", ""))
    console.print(table)
    return 0


def _show(manager: SDDProfileManager, name: str, as_json: bool) -> int:
    profile = manager.get_profile(name)
    if profile is None:
        console.print(f"[red]Profile not found:[/] {name}")
        return 1
    if as_json:
        print(json.dumps(profile.to_dict(), indent=2))
        return 0
    table = Table(title=f"Profile: {name}")
    table.add_column("Phase", style="cyan")
    table.add_column("Model")
    for phase in SDD_PHASES:
        table.add_row(phase, profile.model_assignments.get(phase, "default"))
    console.print(table)
    return 0


def _create(manager: SDDProfileManager, name: str, description: str, base: str | None) -> int:
    assignments: dict[str, str] = {}
    if base is not None:
        base_profile = manager.get_profile(base)
        if base_profile is None:
            console.print(f"[red]Base profile not found:[/] {base}")
            return 1
        assignments = dict(base_profile.model_assignments)
        if not description:
            description = f"Copied from {base}"
    manager.create_profile(name, description=description, model_assignments=assignments)
    console.print(f"[green]Created profile[/] {name}")
    return 0


def _set_phase(manager: SDDProfileManager, name: str, phase: str, model: str) -> int:
    profile = manager.get_profile(name)
    if profile is None:
        console.print(f"[red]Profile not found:[/] {name}. Create it first with 'profile create'.")
        return 1
    assignments = dict(profile.model_assignments)
    assignments[phase] = model
    manager.create_profile(name, description=profile.description, model_assignments=assignments)
    console.print(f"[green]Set[/] {name}.{phase} = {model}")
    return 0


def _delete(manager: SDDProfileManager, name: str) -> int:
    if name in manager.DEFAULT_PROFILES:
        console.print(f"[yellow]Cannot delete the built-in profile:[/] {name}")
        return 1
    if manager.delete_profile(name):
        console.print(f"[green]Deleted profile[/] {name}")
        return 0
    console.print(f"[red]Profile not found:[/] {name}")
    return 1
