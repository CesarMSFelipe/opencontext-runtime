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
from rich.console import Console
from rich.table import Table

console = Console()

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
            "  opencontext models show                     Show role -> model\n"
            "  opencontext models set-role generate opus   Use opus for generation\n"
            "  opencontext models set-role classify haiku  Use haiku for classification\n"
            "  opencontext models set-default sonnet       Default model for unset roles"
        ),
    )
    sub = parser.add_subparsers(dest="models_command", required=True)
    sub.add_parser("show", help="Show the default and per-role model map.")
    set_role = sub.add_parser("set-role", help="Set the model for one role.")
    set_role.add_argument("role", choices=ROLES)
    set_role.add_argument("model", help="Model id/hint (e.g. opus, sonnet, haiku, 5.4-mini).")
    set_default = sub.add_parser("set-default", help="Set the default model for unset roles.")
    set_default.add_argument("model")


def handle_models(args: Any) -> int:
    """Dispatch a ``models`` subcommand. Returns a process exit code."""
    cfg_path = _find_config()
    if cfg_path is None:
        console.print("[red]No opencontext.yaml found.[/] Run 'opencontext init' first.")
        return 1

    command = args.models_command
    if command == "show":
        return _show(cfg_path)
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
    roles = models.get("roles", {}) or {}
    table = Table(title="Models — provider is fixed by your agent CLI")
    table.add_column("Role", style="cyan")
    table.add_column("Model")
    table.add_row("default", str(default))
    for role in ROLES:
        entry = roles.get(role) or {}
        table.add_row(role, str(entry.get("model", "(default)")))
    console.print(table)
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
