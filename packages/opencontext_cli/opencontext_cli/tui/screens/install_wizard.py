"""InstallWizard — guided 5-step install wizard."""

from __future__ import annotations

from enum import auto, Enum
from typing import Any, ClassVar

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.reactive import reactive
    from textual.screen import Screen
    from textual.widgets import Footer, Static
except ImportError:
    Screen = object  # type: ignore[assignment,misc]
    ComposeResult = Any  # type: ignore[assignment]
    Binding = object  # type: ignore[assignment]
    reactive = lambda default: default  # type: ignore[assignment]


class WizardStep(Enum):
    """Sequential steps of the install wizard."""

    WELCOME = auto()
    DETECT_AGENTS = auto()
    MEMORY = auto()
    FLOW_MODE = auto()
    CONFIRM = auto()


class InstallWizard(Screen):  # type: ignore[misc,valid-type]
    """Guided 5-step install wizard."""

    BINDINGS: ClassVar[list] = [
        Binding("n", "next_step", "Next"),
        Binding("p", "prev_step", "Back"),
        Binding("escape", "dismiss", "Cancel"),
    ]

    DEFAULT_CSS = """
    InstallWizard { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #wizard-content { height: 1fr; }
    #wizard-nav { height: 3; }
    """

    step: reactive[WizardStep] = reactive(WizardStep.WELCOME)  # type: ignore[valid-type]

    def compose(self) -> ComposeResult:
        yield Static("", id="wizard-content", markup=True)
        yield Static("", id="wizard-nav", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._render_step()

    def watch_step(self, _: WizardStep) -> None:
        self._render_step()

    def _render_step(self) -> None:
        try:
            content = self.query_one("#wizard-content", Static)
            content.update(self._step_content())
            nav = self.query_one("#wizard-nav", Static)
            nav.update(self._nav_hint())
        except Exception:
            pass

    def _step_content(self) -> str:
        step = self.step
        steps = list(WizardStep)
        idx = steps.index(step) + 1
        total = len(steps)
        header = f"[bold]OpenContext Install Wizard[/bold]  [dim]Step {idx}/{total}[/dim]\n"

        if step == WizardStep.WELCOME:
            try:
                import importlib.metadata

                version = importlib.metadata.version("opencontext-cli")
            except Exception:
                version = "unknown"
            return (
                header
                + "\n[bold]Welcome to OpenContext![/bold]\n\n"
                + f"Version: {version}\n\n"
                + "This wizard will guide you through setting up OpenContext\n"
                + "for your project in a few quick steps.\n\n"
                + "Press [bold][n][/bold] to begin."
            )

        if step == WizardStep.DETECT_AGENTS:
            detected = _detect_agent_clis()
            agent_lines = "\n".join(
                f"  [green]✓[/green] {name}" if found else f"  [dim]✗ {name}[/dim]"
                for name, found in detected.items()
            )
            return (
                header
                + "\n[bold]Detecting agent CLIs...[/bold]\n\n"
                + agent_lines
                + "\n\nPress [bold][n][/bold] to continue."
            )

        if step == WizardStep.MEMORY:
            return (
                header
                + "\n[bold]Memory backend:[/bold]\n\n"
                + "  [bold][1][/bold] Engram  [dim](recommended — cross-session semantic memory)[/dim]\n"
                + "  [bold][2][/bold] Local only  [dim](SQLite, project-scoped)[/dim]\n"
                + "  [bold][3][/bold] Off  [dim](no memory persistence)[/dim]\n\n"
                + "Press [bold][n][/bold] to continue."
            )

        if step == WizardStep.FLOW_MODE:
            return (
                header
                + "\n[bold]SDD flow mode:[/bold]\n\n"
                + "  [bold][1][/bold] Hybrid  [dim](recommended — auto-advances, pauses on risk)[/dim]\n"
                + "  [bold][2][/bold] Automatic  [dim](fully autonomous)[/dim]\n"
                + "  [bold][3][/bold] Stepwise  [dim](pause after every phase)[/dim]\n\n"
                + "Press [bold][n][/bold] to continue."
            )

        if step == WizardStep.CONFIRM:
            return (
                header
                + "\n[bold]Ready to install.[/bold]\n\n"
                + "OpenContext will be configured with your selections.\n\n"
                + "Press [bold][Enter / n][/bold] to apply or [bold][Escape][/bold] to cancel."
            )

        return header

    def _nav_hint(self) -> str:
        steps = list(WizardStep)
        idx = steps.index(self.step)
        parts: list[str] = []
        if idx > 0:
            parts.append("[bold][p][/bold] Back")
        if idx < len(steps) - 1:
            parts.append("[bold][n][/bold] Next")
        else:
            parts.append("[bold][n][/bold] Apply")
        parts.append("[bold][Esc][/bold] Cancel")
        return "  " + "   ".join(parts)

    def action_next_step(self) -> None:
        steps = list(WizardStep)
        idx = steps.index(self.step)
        if idx < len(steps) - 1:
            self.step = steps[idx + 1]
        else:
            # Final step — dismiss as confirmed
            self.dismiss(True)

    def action_prev_step(self) -> None:
        steps = list(WizardStep)
        idx = steps.index(self.step)
        if idx > 0:
            self.step = steps[idx - 1]

    def action_dismiss(self) -> None:
        self.app.pop_screen()


def _detect_agent_clis() -> dict[str, bool]:
    """Probe PATH for known agent CLIs."""
    import shutil

    candidates = {
        "claude-code": "claude",
        "cursor": "cursor",
        "codex": "codex",
        "aider": "aider",
        "continue": "continue",
    }
    return {name: shutil.which(cmd) is not None for name, cmd in candidates.items()}
