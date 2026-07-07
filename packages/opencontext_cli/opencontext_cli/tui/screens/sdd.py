"""SddScreen — SDD workspace: per-change artifacts and the next step.

Reads ``.opencontext/sdd/context.json`` plus ``openspec/changes/*/`` and
reuses the canonical disk-state resolver (``opencontext_sdd.status.Resolve``)
to report each change's artifact states and recommended next phase.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static

from opencontext_cli.tui.brand import DIM, ERROR, PRIMARY, SUCCESS, WARNING, BrandBar

_ARTIFACT_ORDER = ("proposal", "specs", "design", "tasks", "verify-report")
_STATE_ICONS = {"done": "✓", "partial": "◐", "missing": "✗"}

# Planning/read-only phases the TUI may execute directly; mutating or closing
# steps (apply writes code, archive closes the change) need explicit approval
# and stay on the CLI.
_RUNNABLE_PHASES = frozenset({"explore", "propose", "spec", "design", "tasks", "verify"})
_APPROVAL_PHASES = frozenset({"apply", "archive"})


def next_phase_action(next_recommended: str) -> str:
    """Classify a change's next recommended step for the TUI runner.

    Returns ``"run"`` for phases the TUI can execute without approval,
    ``"approval"`` for steps that require explicit approval (apply/archive),
    and ``"blocked"`` for non-phase states (review, resolve-blockers, ...).
    """
    if next_recommended in _RUNNABLE_PHASES:
        return "run"
    if next_recommended in _APPROVAL_PHASES:
        return "approval"
    return "blocked"


def read_sdd_context(root: Path) -> dict[str, Any]:
    """Read ``.opencontext/sdd/context.json``; empty dict on miss."""
    context_path = root / ".opencontext" / "sdd" / "context.json"
    try:
        data = json.loads(context_path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def list_sdd_changes(root: Path) -> list[dict[str, Any]]:
    """Artifact states + next step per ``openspec/changes/*`` change."""
    changes_root = root / "openspec" / "changes"
    if not changes_root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for change_dir in sorted(p for p in changes_root.iterdir() if p.is_dir()):
        entry: dict[str, Any] = {"change": change_dir.name, "artifacts": {}, "next": "unknown"}
        try:
            from opencontext_sdd.status import Resolve

            status = Resolve(change_dir.name, cwd=str(root))
            entry["artifacts"] = dict(status.artifacts)
            entry["next"] = status.nextRecommended
        except Exception:
            # Resolver unavailable — a plain presence scan keeps the screen honest.
            for name, filename in (
                ("proposal", "proposal.md"),
                ("design", "design.md"),
                ("tasks", "tasks.md"),
                ("verify-report", "verify-report.md"),
            ):
                entry["artifacts"][name] = "done" if (change_dir / filename).exists() else "missing"
            specs = list((change_dir / "specs").glob("*/spec.md"))
            entry["artifacts"]["specs"] = "done" if specs else "missing"
        entries.append(entry)
    return entries


class SddScreen(Screen[None]):
    """SDD workspace: change list with artifact states and next steps.

    ``r`` executes the next dependency-ready phase through the SDD runner when
    that phase needs no approval; apply/archive are refused with a CLI hint.
    """

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape,q", "dismiss", "Back"),
        Binding("r", "run_next", "Run next phase"),
    ]

    DEFAULT_CSS = """
    SddScreen { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #sdd-content { height: 1fr; }
    #sdd-status { height: auto; }
    """

    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self._root = root or Path(".")

    def compose(self) -> ComposeResult:
        yield BrandBar()
        yield Static(
            "[bold]SDD workspace[/]\n"
            "[dim]Changes, phase artifacts and the next step — "
            "r runs the next phase when it needs no approval[/]",
            markup=True,
        )
        yield Static("", id="sdd-content", markup=True)
        yield Static("", id="sdd-status", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sdd-content", Static).update(self._screen_markup())

    def action_run_next(self) -> None:
        """Execute the next recommended phase for the workspace's single change."""
        status = self.query_one("#sdd-status", Static)
        entries = list_sdd_changes(self._root)
        if not entries:
            status.update("[dim]No SDD changes to advance.[/dim]")
            return
        if len(entries) > 1:
            status.update(
                f"[{DIM}]Multiple changes — run 'opencontext sdd continue <change>' "
                "from the CLI to pick one.[/]"
            )
            return
        entry = entries[0]
        phase = str(entry["next"])
        action = next_phase_action(phase)
        if action == "approval":
            status.update(
                f"[{WARNING}]'{escape(phase)}' requires approval — run "
                f"'opencontext sdd {escape(phase)}' from the CLI to approve it.[/]"
            )
            return
        if action == "blocked":
            status.update(f"[{DIM}]Next step '{escape(phase)}' is not runnable from the TUI.[/]")
            return
        try:
            import opencontext_sdd.runner as _runner

            envelope = _runner.run_phase(phase, change=str(entry["change"]), cwd=str(self._root))
        except Exception as exc:  # a runner failure must render, not crash
            status.update(f"[{ERROR}]Phase '{escape(phase)}' failed: {escape(str(exc))}[/]")
            return
        color = SUCCESS if envelope.status in ("ok", "partial") else ERROR
        status.update(
            f"[{color}]{escape(phase)}: {escape(envelope.status)}[/] — "
            f"{escape(envelope.executive_summary)}"
        )
        self.query_one("#sdd-content", Static).update(self._screen_markup())

    def _screen_markup(self) -> str:
        lines: list[str] = []
        context = read_sdd_context(self._root)
        if context:
            store = context.get("artifactStore", "?")
            tdd_mode = context.get("tdd_mode", "?")
            lines.append(
                f"[{DIM}]artifact store: {escape(str(store))} · tdd: {escape(str(tdd_mode))}[/]"
            )
            lines.append("")
        entries = list_sdd_changes(self._root)
        if not entries:
            lines.append("[dim]No SDD changes found under openspec/changes/.[/dim]")
            return "\n".join(lines)
        for entry in entries:
            lines.append(
                f"[bold]{escape(entry['change'])}[/]  next: [{PRIMARY}]{escape(entry['next'])}[/]"
            )
            marks: list[str] = []
            for name in _ARTIFACT_ORDER:
                state = str(entry["artifacts"].get(name, "missing"))
                icon = _STATE_ICONS.get(state, "?")
                color = {"done": SUCCESS, "partial": WARNING}.get(state, ERROR)
                marks.append(f"[{color}]{icon}[/] {name}")
            lines.append("  " + "   ".join(marks))
            lines.append("")
        return "\n".join(lines)

    def action_dismiss(self, result: Any = None) -> None:  # type: ignore[override]
        self.app.pop_screen()
