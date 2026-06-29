"""Per-role model CLI — set which model each functional role uses.

OpenContext runs on top of your agent CLI, which fixes the PROVIDER
(claude-code -> Anthropic, codex -> OpenAI). This command sets which MODEL each
role uses; the model is sent to the agent as an MCP sampling hint, so e.g.
exploration can use a cheap model and design a strong one — all within the
agent's own provider. A role is just a model name (no provider needed).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from rich.table import Table

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console

ROLES = (
    "classify",
    "retrieve",
    "rerank",
    "compress",
    "generate",
    "validate",
    "audit",
    "summarize",
    "orchestrate",
)

# Per-persona is the recommended way to route SDD models: each persona owns its
# SDD phase(s), so "the Architect uses opus" reads better than a phase or role id.
# short name -> (persona id written to sdd.persona_models, SDD phase(s) it covers)
PERSONAS: dict[str, tuple[str, str]] = {
    "explorer": ("oc-explorer", "explore"),
    "orchestrator": ("oc-orchestrator", "propose/spec/tasks"),
    "architect": ("oc-architect", "design"),
    "builder": ("oc-builder", "apply"),
    "tester": ("oc-tester", "test (TDD)"),
    "reviewer": ("oc-reviewer", "verify/review"),
    "professor": ("oc-professor", "teaching"),
}


def _find_config(start: Path | None = None) -> Path | None:
    """Locate the nearest opencontext.yaml from ``start`` (or cwd) upward."""
    cur = (start or Path.cwd()).resolve()
    for directory in (cur, *cur.parents):
        candidate = directory / "opencontext.yaml"
        if candidate.exists():
            return candidate
    return None


def add_models_parser(subparsers: Any) -> None:
    """Add the ``models`` command parser."""
    parser = subparsers.add_parser(
        "models",
        help="Set which model each role uses (within your agent's provider).",
        description=(
            "Set the model per functional role. Your agent CLI fixes the provider; "
            "OpenContext routes the model per role via MCP sampling hints.\n\n"
            "  opencontext models show                       Show persona/role -> model\n"
            "  opencontext models set-persona architect opus Use opus for the design phase\n"
            "  opencontext models set-default sonnet         Default (your client's model)\n"
            "  opencontext models set-role generate opus     Advanced: per functional role"
        ),
    )
    sub = parser.add_subparsers(dest="models_command", required=True)
    sub.add_parser("show", help="Show the default, per-persona, and per-role model map.")
    set_persona = sub.add_parser(
        "set-persona", help="Set the model for an SDD persona (recommended)."
    )
    set_persona.add_argument("persona", choices=tuple(PERSONAS))
    set_persona.add_argument("model", help="Model id/hint (e.g. opus, sonnet, haiku, 5.4-mini).")
    set_role = sub.add_parser("set-role", help="Advanced: set the model for one functional role.")
    set_role.add_argument("role", choices=ROLES)
    set_role.add_argument("model", help="Model id/hint (e.g. opus, sonnet, haiku, 5.4-mini).")
    set_default = sub.add_parser("set-default", help="Set the default model for unset personas.")
    set_default.add_argument("model")


def handle_models(args: Any) -> int:
    """Dispatch a ``models`` subcommand. Returns a process exit code."""
    cfg_path = _find_config()
    if cfg_path is None:
        eprint("No opencontext.yaml found. Run 'opencontext init' first.")
        return 1

    command = args.models_command
    if command == "show":
        return _show(cfg_path)
    if command == "set-persona":
        return _set_persona(cfg_path, args.persona, args.model)
    if command == "set-role":
        return _set_role(cfg_path, args.role, args.model)
    if command == "set-default":
        return _set_default(cfg_path, args.model)
    return 1


def _load(cfg_path: Path) -> dict[str, Any]:
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}


def _save(cfg_path: Path, data: dict[str, Any]) -> None:
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _show(cfg_path: Path) -> int:
    data = _load(cfg_path)
    models = data.get("models", {}) or {}
    default = (models.get("default", {}) or {}).get("model", "—")
    persona_models = (data.get("sdd", {}) or {}).get("persona_models", {}) or {}

    console.header("Models")
    console.print(f"[bold]default[/] (your client's model): {default}")

    personas = Table(title="Per-persona models (recommended) — SDD phase routing")
    personas.add_column("Persona", style="cyan")
    personas.add_column("SDD phase(s)", style="dim")
    personas.add_column("Model")
    for name, (persona_id, phases) in PERSONAS.items():
        personas.add_row(name, phases, str(persona_models.get(persona_id, "(default)")))
    console.print(personas)

    roles = models.get("roles", {}) or {}
    if any((roles.get(r) or {}).get("model") for r in ROLES):
        advanced = Table(title="Per-role models (advanced fallback)")
        advanced.add_column("Role", style="cyan")
        advanced.add_column("Model")
        for role in ROLES:
            entry = roles.get(role) or {}
            advanced.add_row(role, str(entry.get("model", "(default)")))
        console.print(advanced)
    return 0


def _set_persona(cfg_path: Path, persona: str, model: str) -> int:
    persona_id = PERSONAS[persona][0]
    data = _load(cfg_path)
    sdd = data.setdefault("sdd", {})
    persona_models = sdd.setdefault("persona_models", {})
    persona_models[persona_id] = model
    _save(cfg_path, data)
    console.print(f"[green]Set[/] sdd.persona_models.{persona_id} = {model}  ({persona})")
    return 0


def _set_role(cfg_path: Path, role: str, model: str) -> int:
    data = _load(cfg_path)
    models = data.setdefault("models", {})
    roles = models.setdefault("roles", {})
    # A role is just a model — the provider is the agent's, not OpenContext's.
    roles[role] = {"model": model}
    _save(cfg_path, data)
    console.print(f"[green]Set[/] models.roles.{role}.model = {model}")
    return 0


def _set_default(cfg_path: Path, model: str) -> int:
    data = _load(cfg_path)
    models = data.setdefault("models", {})
    default = models.setdefault("default", {})
    default["model"] = model
    _save(cfg_path, data)
    console.print(f"[green]Set[/] models.default.model = {model}")
    return 0
