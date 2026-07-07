"""TddGatesScreen — the latest runs' quality gates with TDD evidence focus.

Reuses the run-bundle readers behind RunsScreen/RunDetailScreen
(:func:`list_run_rows` / :func:`load_run_detail`) to render, per recent
run, the gates.json name/status table and the run.json ``tdd`` block
(red/green classification, commands, exit codes). Shows an honest empty
state when no runs are persisted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from opencontext_cli.tui.brand import DIM, ERROR, PRIMARY, SUCCESS, BrandBar
from opencontext_cli.tui.screens.runs import _GATE_ICONS, list_run_rows, load_run_detail

_RUN_LIMIT = 5


def latest_tdd_rows(root: Path, *, limit: int = _RUN_LIMIT) -> list[dict[str, Any]]:
    """Gate + TDD evidence for the newest ``limit`` persisted runs."""
    rows: list[dict[str, Any]] = []
    for run_row in list_run_rows(root)[:limit]:
        detail = load_run_detail(run_row["run_dir"])
        rows.append(
            {
                "run_id": run_row["run_id"],
                "workflow": run_row["workflow"],
                "status": run_row["status"],
                "gates": detail["gates"],
                "tdd": detail["tdd"],
            }
        )
    return rows


class TddGatesScreen(Screen[None]):
    """Quality gates and RED/GREEN TDD evidence for the latest persisted runs."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape,q", "dismiss", "Back"),
    ]

    DEFAULT_CSS = """
    TddGatesScreen { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #tdd-gates-scroll { height: 1fr; }
    """

    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self._root = root or Path(".")

    def compose(self) -> ComposeResult:
        yield BrandBar()
        yield Static(
            "[bold]TDD Gates[/]\n[dim]Latest runs' gates and RED/GREEN evidence[/]",
            markup=True,
        )
        with VerticalScroll(id="tdd-gates-scroll"):
            yield Static("", id="tdd-gates-content", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#tdd-gates-content", Static).update(self._gates_markup())

    def _gates_markup(self) -> str:
        rows = latest_tdd_rows(self._root)
        if not rows:
            return "[dim]No persisted runs found — nothing to show yet.[/dim]"
        sections: list[str] = []
        for row in rows:
            lines = [
                f"[bold]{escape(row['run_id'])}[/]  [{PRIMARY}]{escape(row['workflow'])}[/]  "
                f"{escape(row['status'])}"
            ]
            if row["gates"]:
                lines.append("  [bold]Gates:[/]")
                for gate in row["gates"]:
                    icon = _GATE_ICONS.get(gate["status"], "?")
                    color = SUCCESS if gate["status"] == "passed" else ERROR
                    if gate["status"] == "skipped":
                        color = DIM
                    lines.append(
                        f"    [{color}]{icon}[/] {escape(gate['name'])}  {escape(gate['status'])}"
                    )
            lines.append("  [bold]TDD:[/]")
            tdd = row["tdd"]
            if not tdd:
                lines.append(f"    [{DIM}]no TDD evidence recorded for this run[/]")
            else:
                lines.append(f"    mode: {escape(str(tdd.get('mode', '?')))}")
                for phase in ("red", "green", "regression"):
                    evidence = tdd.get(phase)
                    if not isinstance(evidence, dict):
                        continue
                    color = ERROR if phase == "red" else SUCCESS
                    lines.append(
                        f"    [{color}]{phase}[/]: "
                        f"{escape(str(evidence.get('classification') or '?'))}  "
                        f"exit {escape(str(evidence.get('exit_code')))}  "
                        f"[{DIM}]{escape(str(evidence.get('command') or '?'))}[/]"
                    )
                for proof in ("red_proven", "green_proven"):
                    if proof in tdd:
                        value = bool(tdd[proof])
                        color = SUCCESS if value else ERROR
                        lines.append(f"    {proof}: [{color}]{'yes' if value else 'no'}[/]")
                violation = tdd.get("violation")
                if violation:
                    lines.append(f"    [{ERROR}]violation:[/] {escape(str(violation))}")
            sections.append("\n".join(lines))
        return "\n\n".join(sections)

    def action_dismiss(self, result: Any = None) -> None:  # type: ignore[override]
        self.app.pop_screen()
