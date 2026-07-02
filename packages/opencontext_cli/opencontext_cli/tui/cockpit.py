"""CockpitScreen — live run-state dashboard for the oc-new agentic flow.

Polls OcNewStore.latest() every 3 seconds and renders current run state:
phase, progress, budget, and last event. Mounts BrandBar from tui/brand.py.
Idle state is shown when no run exists.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

from opencontext_cli.tui.brand import DIM, PRIMARY, WARNING, BrandBar

_PHASE_ICONS: dict[str, str] = {
    "pending": "○",
    "running": "→",
    "passed": "✓",
    "warning": "⚠",
    "failed": "✗",
    "blocked": "⊘",
    "skipped": "-",
}


class CockpitScreen(Screen[None]):
    """Live dashboard showing the current oc-new run state."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("n", "new_change", "New change"),
        Binding("m", "memory", "Memory"),
        Binding("k", "context", "KG/Context"),
        Binding("g", "graph", "Graph"),
        Binding("b", "budget", "Budget"),
        Binding("h", "harness", "Harness"),
        Binding("r", "receipt", "Receipt"),
        Binding("l", "learning", "Learning"),
        Binding("s", "settings", "Settings"),
        Binding("q", "quit", "Quit"),
    ]

    DEFAULT_CSS = """
    CockpitScreen { background: #0B0F14; color: #E6EDF3; }
    #cockpit { height: 1fr; padding: 1 2; }
    #project-summary { height: auto; padding: 0 0 1 0; }
    #run-state { height: 1fr; color: #E6EDF3; }
    Footer { background: #11161D; }
    """

    def compose(self) -> ComposeResult:
        yield BrandBar()
        with Vertical(id="cockpit"):
            yield Static("", id="project-summary", markup=True)
            yield Static("", id="run-state", markup=True)
            # NOTE: PR6 — additive workflow-state panel (read from WorkflowState).
            yield Static("", id="workflow-panel", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(3.0, self._refresh_state)
        self._refresh_state()

    def _refresh_state(self) -> None:
        """Non-blocking poll of OcNewStore.latest() — updates Static widgets."""
        try:
            from opencontext_core.oc_new.store import OcNewStore

            store = OcNewStore(".")
            state = store.latest()
        except Exception:
            state = None

        summary_widget = self.query_one("#project-summary", Static)
        run_widget = self.query_one("#run-state", Static)
        workflow_widget = self.query_one("#workflow-panel", Static)

        if state is None:
            summary_widget.update(f"[{DIM}]No active run — press N to start a new change.[/]")
            run_widget.update("")
            workflow_widget.update("")
            return

        summary_widget.update(
            f"[bold {PRIMARY}]Run:[/] {state.identity.run_id}  [{DIM}]{state.task[:60]}[/]"
        )
        run_widget.update(_render_phases(state))
        # NOTE: PR6 — project live state into WorkflowState; render panel.
        try:
            from opencontext_core.workflow.panel import render_workflow_panel
            from opencontext_core.workflow.state import WorkflowState

            workflow = WorkflowState.project_from(state)
            workflow_widget.update(render_workflow_panel(workflow))
        except Exception:
            workflow_widget.update("")

    def action_settings(self) -> None:
        """Navigate to the config screen."""
        from opencontext_cli.tui.app import ConfigScreen

        self.app.push_screen(ConfigScreen())

    def action_quit(self) -> None:
        """Exit the application."""
        self.app.exit()

    def action_new_change(self) -> None:
        """Open NewChangeScreen and start an oc-new run on submit."""
        start_new_change(self.app, refresh=self._refresh_state)

    def action_memory(self) -> None:
        """Open the memory browser screen."""
        from opencontext_cli.tui.screens.memory import MemoryBrowserScreen

        self.app.push_screen(MemoryBrowserScreen())

    def action_context(self) -> None:
        """Open the KG/context viewer screen."""
        from opencontext_cli.tui.screens.context import ContextViewerScreen

        self.app.push_screen(ContextViewerScreen())

    def action_graph(self) -> None:
        """Open graph viewer for the active run, else KG."""
        from opencontext_cli.tui.graph.models import GraphMode
        from opencontext_cli.tui.screens.graph import GraphScreen

        run_id = _latest_run_id()
        if run_id:
            self.app.push_screen(GraphScreen(mode=GraphMode.RUN, run_id=run_id, root="."))
        else:
            self.app.push_screen(GraphScreen(mode=GraphMode.KG, root="."))

    def action_budget(self) -> None:
        """Open the budget ledger screen."""
        from opencontext_cli.tui.screens.budget import BudgetScreen

        self.app.push_screen(BudgetScreen())

    def action_harness(self) -> None:
        """Open harness report for the active run."""
        from opencontext_cli.tui.app import _latest_run_dir
        from opencontext_cli.tui.screens.harness import HarnessPanel

        self.app.push_screen(HarnessPanel(run_dir=_latest_run_dir()))

    def action_receipt(self) -> None:
        """Open receipt for the active run."""
        from opencontext_cli.tui.app import _latest_run_dir
        from opencontext_cli.tui.screens.receipt import ReceiptViewer

        self.app.push_screen(ReceiptViewer(run_dir=_latest_run_dir()))

    def action_learning(self) -> None:
        """Open the learning inbox (pending evolution proposals)."""
        from opencontext_cli.tui.screens.learning_inbox import LearningInbox

        self.app.push_screen(LearningInbox())


def start_new_change(app: object, *, refresh: Callable[[], None] | None = None) -> None:
    """Open NewChangeScreen and start an oc-new run on submit."""
    from opencontext_cli.tui.screens.new_change import NewChangeScreen

    app_any = app
    refresh_fn = refresh

    # NOTE: object typing avoids importing Textual App just for one callback.
    def _start(result: dict[str, str] | None) -> None:
        if not result:
            return
        try:
            from opencontext_core.agentic.config import (
                AgenticFlowConfig,
                FlowMode,
                GitMode,
                MemoryMode,
                OpenSpecMode,
            )
            from opencontext_core.oc_new.conductor import OcNewConductor

            cfg = AgenticFlowConfig(
                flow_mode=FlowMode(result["flow"]),
                memory_mode=MemoryMode(result["memory"]),
                openspec_mode=OpenSpecMode(result["openspec"]),
                git_mode=GitMode(result["git"]),
            )
            OcNewConductor(".").start(result["objective"], config=cfg)
            if refresh_fn is not None:
                refresh_fn()
        except Exception:
            pass

    app_any.push_screen(NewChangeScreen(), _start)  # type: ignore[attr-defined]


def _latest_run_id() -> str | None:
    try:
        from opencontext_core.oc_new.store import OcNewStore

        state = OcNewStore(".").latest()
        return None if state is None else state.identity.run_id
    except Exception:
        return None


def _render_phases(state: object) -> str:
    """Render phase table from OcNewRunState for the run-state Static widget."""
    lines: list[str] = []
    try:
        phases = getattr(state, "phases", [])
        current = getattr(state, "current_phase", None)
        for phase in phases:
            icon = _PHASE_ICONS.get(phase.status, "?")
            colour = PRIMARY if phase.name == current else DIM
            lines.append(f"  [{colour}]{icon} {phase.name:<12} {phase.status}[/]")
        na = getattr(state, "next_action", None)
        if na:
            lines.append("")
            lines.append(f"  [{WARNING}]Next:[/] {na.kind} — {na.instruction[:80]}")
    except Exception as exc:
        lines.append(f"[red]Error rendering state: {exc}[/]")
    return "\n".join(lines)
