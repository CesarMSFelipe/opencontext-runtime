"""Persona CLI — inspect and configure OpenContext's selectable agent personas.

Personas drive the SDD phases (Explorer→explore, Architect→design, Builder→apply,
Tester→tests, Reviewer→verify/review, Orchestrator→propose/spec/tasks) and can
each be pinned to a provider model. `setup` writes them as native agent files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from rich.table import Table

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console
from opencontext_core.personas import PERSONAS, delegation_personas, get_persona, public_personas


def add_persona_parser(subparsers: Any) -> None:
    """Add the ``persona`` command parser."""
    parser = subparsers.add_parser(
        "persona",
        help="Inspect and configure OpenContext agent personas.",
        description=(
            "OpenContext personas drive the SDD phases and can each be pinned to a model.\n\n"
            "  opencontext persona list                       List the personas\n"
            "  opencontext persona show oc-architect          Show a persona's full prompt\n"
            "  opencontext persona models                     Show per-persona model assignments\n"
            "  opencontext persona set-model oc-orchestrator opus   Pin a model to a persona\n\n"
            "Personas are written as native agent files by `opencontext setup`."
        ),
    )
    sub = parser.add_subparsers(dest="persona_command", required=True)
    lst = sub.add_parser("list", help="List available personas.")
    lst.add_argument("--all", action="store_true", help="Include delegation subagents.")
    lst.add_argument("--delegates", action="store_true", help="Show only delegation subagents.")
    show = sub.add_parser("show", help="Show a persona's description and prompt.")
    show.add_argument("id", help="Persona id (e.g. oc-orchestrator, oc-architect, oc-builder).")
    sub.add_parser("models", help="Show per-persona model assignments.")
    setm = sub.add_parser("set-model", help="Pin a provider model to a persona.")
    setm.add_argument("id", help="Persona id (e.g. oc-orchestrator).")
    setm.add_argument("model", help="Model name (e.g. opus, sonnet, haiku, claude-opus-4-8).")
    setm.add_argument("--root", default=".", help="Project root holding opencontext.yaml.")


def handle_persona(args: Any) -> int:
    """Dispatch a ``persona`` subcommand. Returns a process exit code."""
    if args.persona_command == "list":
        if getattr(args, "all", False):
            rows = PERSONAS
        elif getattr(args, "delegates", False):
            rows = delegation_personas()
        else:
            rows = public_personas()
        console.header("Personas")
        table = Table(title=f"OpenContext personas ({len(rows)})")
        table.add_column("Id", style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Description")
        for persona in rows:
            table.add_row(persona.id, persona.name, persona.description)
        console.print(table)
        return 0

    if args.persona_command == "show":
        found = get_persona(args.id)
        if found is None:
            eprint(f"Unknown persona: {args.id}")
            eprint(f"  Available: {', '.join(p.id for p in PERSONAS)}")
            return 1
        console.print(f"[bold]{found.name}[/] [dim]({found.id})[/]")
        console.print(found.description)
        console.print()
        console.print(found.system_prompt)
        return 0

    if args.persona_command == "models":
        cfg_path = Path(getattr(args, "root", ".")) / "opencontext.yaml"
        assignments: dict[str, str] = {}
        if cfg_path.exists():
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            assignments = (data.get("sdd") or {}).get("persona_models", {}) or {}
        table = Table(title="Per-persona model assignments")
        table.add_column("Persona", style="cyan")
        table.add_column("Model")
        for persona in PERSONAS:
            table.add_row(persona.id, assignments.get(persona.id) or "[dim]default[/]")
        console.print(table)
        return 0

    if args.persona_command == "set-model":
        if get_persona(args.id) is None:
            eprint(f"Unknown persona: {args.id}")
            eprint(f"  Available: {', '.join(p.id for p in PERSONAS)}")
            return 1
        cfg_path = Path(getattr(args, "root", ".")) / "opencontext.yaml"
        if not cfg_path.exists():
            eprint(f"No opencontext.yaml at {cfg_path} — run `opencontext install`.")
            return 1
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        sdd = data.setdefault("sdd", {})
        persona_models = sdd.setdefault("persona_models", {})
        persona_models[args.id] = args.model
        cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        console.print(f"[green]✓[/] {args.id} → [cyan]{args.model}[/]")
        return 0
    return 1
