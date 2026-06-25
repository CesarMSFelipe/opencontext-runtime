"""HarnessPanel — displays the latest harness-report.json for the current run."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.screen import Screen
    from textual.widgets import Footer, Static
except ImportError:
    Screen = object  # type: ignore[assignment,misc]
    ComposeResult = Any  # type: ignore[assignment]
    Binding = object  # type: ignore[assignment]


class HarnessPanel(Screen):  # type: ignore[misc,valid-type]
    """Displays the latest harness-report.json for the current run."""

    BINDINGS: ClassVar[list] = [
        Binding("escape,q", "dismiss", "Back"),
    ]

    DEFAULT_CSS = """
    HarnessPanel { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #harness-content { height: 1fr; }
    """

    def __init__(self, run_dir: Path | None = None) -> None:
        super().__init__()
        self._run_dir = run_dir

    def compose(self) -> ComposeResult:
        yield Static("", id="harness-content", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        content = self.query_one("#harness-content", Static)
        content.update(self._load_content())

    def _load_content(self) -> str:
        if self._run_dir is None:
            return "[dim]No active run.[/dim]"
        report_path = self._run_dir / "harness-report.json"
        if not report_path.exists():
            return "[dim]harness-report.json not found.[/dim]"
        try:
            from opencontext_core.harness.models import HarnessReport

            report = HarnessReport.model_validate_json(report_path.read_text(encoding="utf-8"))
            status_color = "green" if report.passed else "red"
            lines = [
                f"[bold]Run:[/] {report.run_id}",
                f"[bold]Change:[/] {report.change_id}",
                f"[bold]Status:[/] [{status_color}]"
                f"{'PASSED' if report.passed else 'FAILED'}"
                f"[/{status_color}]",
            ]
            if report.failures:
                lines.append("")
                lines.append("[bold]Failures:[/]")
                lines.extend(f"  [red]- {f}[/red]" for f in report.failures)
            return "\n".join(lines)
        except Exception as exc:
            return f"[red]Error reading harness report: {exc}[/red]"

    def action_dismiss(self) -> None:
        self.app.pop_screen()
