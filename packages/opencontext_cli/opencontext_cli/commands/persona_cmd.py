"""Persona CLI — inspect OpenContext's selectable agent personas.

Three personas ship: OC Orchestrator (coordinate + verify), OC Professor (teach
the why), OC Reviewer (rigorous review). `setup` writes them as native agent
files for editors that support them; this command lists and shows them.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

from opencontext_core.personas import PERSONAS, get_persona

console = Console()


def add_persona_parser(subparsers: Any) -> None:
    """Add the ``persona`` command parser."""
    parser = subparsers.add_parser(
        "persona",
        help="Inspect OpenContext agent personas (orchestrator / professor / reviewer).",
        description=(
            "OpenContext ships three agent personas.\n\n"
            "  opencontext persona list            List the personas\n"
            "  opencontext persona show oc-reviewer Show a persona's full prompt\n\n"
            "Personas are written as native agent files by `opencontext setup`."
        ),
    )
    sub = parser.add_subparsers(dest="persona_command", required=True)
    sub.add_parser("list", help="List available personas.")
    show = sub.add_parser("show", help="Show a persona's description and prompt.")
    show.add_argument("id", help="Persona id (e.g. oc-orchestrator, oc-professor, oc-reviewer).")


def handle_persona(args: Any) -> int:
    """Dispatch a ``persona`` subcommand. Returns a process exit code."""
    if args.persona_command == "list":
        table = Table(title=f"OpenContext personas ({len(PERSONAS)})")
        table.add_column("Id", style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Description")
        for persona in PERSONAS:
            table.add_row(persona.id, persona.name, persona.description)
        console.print(table)
        return 0

    if args.persona_command == "show":
        persona = get_persona(args.id)
        if persona is None:
            console.print(f"[red]Unknown persona:[/] {args.id}")
            console.print(f"  Available: {', '.join(p.id for p in PERSONAS)}")
            return 1
        console.print(f"[bold]{persona.name}[/] [dim]({persona.id})[/]")
        console.print(persona.description)
        console.print()
        console.print(persona.system_prompt)
        return 0
    return 1
