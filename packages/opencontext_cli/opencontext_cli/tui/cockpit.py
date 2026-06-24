"""CockpitScreen — live run-state dashboard for the oc-new agentic flow.

Polls OcNewStore.latest() every 3 seconds and renders current run state:
phase, progress, budget, and last event. Mounts BrandBar from tui/brand.py.
Idle state is shown when no run exists.
"""

from __future__ import annotations

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


class CockpitScreen(Screen):  # type: ignore[misc]
    """Live dashboard showing the current oc-new run state."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("n", "new_change", "New change"),
        Binding("m", "memory", "Memory"),
        Binding("k", "context", "KG/Context"),
        Binding("b", "budget", "Budget"),
        Binding("d", "doctor", "Doctor"),
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

        if state is None:
            summary_widget.update(f"[{DIM}]No active run — press N to start a new change.[/]")
            run_widget.update("")
            return

        summary_widget.update(
            f"[bold {PRIMARY}]Run:[/] {state.identity.run_id}  "
            f"[{DIM}]{state.task[:60]}[/]"
        )
        run_widget.update(_render_phases(state))

    def action_settings(self) -> None:
        """Navigate to the config screen."""
        from opencontext_cli.tui.app import ConfigScreen

        self.app.push_screen(ConfigScreen())

    def action_quit(self) -> None:
        """Exit the application."""
        self.app.exit()

    def action_new_change(self) -> None:
        """Open NewChangeScreen and start an oc-new run on submit."""
        from opencontext_cli.tui.screens.new_change import NewChangeScreen

        def _start(result: dict | None) -> None:
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
                self._refresh_state()
            except Exception:
                pass

        self.app.push_screen(NewChangeScreen(), _start)

    def action_memory(self) -> None:
        """Open the memory browser screen."""
        from opencontext_cli.tui.screens.memory import MemoryBrowserScreen

        self.app.push_screen(MemoryBrowserScreen())

    def action_context(self) -> None:
        """Open the KG/context viewer screen."""
        from opencontext_cli.tui.screens.context import ContextViewerScreen

        self.app.push_screen(ContextViewerScreen())

    def action_budget(self) -> None:
        """Open the budget ledger screen."""
        from opencontext_cli.tui.screens.budget import BudgetScreen

        self.app.push_screen(BudgetScreen())

    def action_doctor(self) -> None:
        """Placeholder — future: open doctor screen."""


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
