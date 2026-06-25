"""ReceiptViewer — displays the PhaseResultEnvelope receipt for a completed run."""

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


class ReceiptViewer(Screen):  # type: ignore[misc,valid-type]
    """Displays receipt.json (PhaseResultEnvelope) for a completed run."""

    BINDINGS: ClassVar[list] = [
        Binding("escape,q", "dismiss", "Back"),
    ]

    DEFAULT_CSS = """
    ReceiptViewer { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #receipt-content { height: 1fr; }
    """

    def __init__(self, run_dir: Path | None = None) -> None:
        super().__init__()
        self._run_dir = run_dir

    def compose(self) -> ComposeResult:
        yield Static("", id="receipt-content", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        content = self.query_one("#receipt-content", Static)
        content.update(self._load_receipt())

    def _load_receipt(self) -> str:
        if self._run_dir is None:
            return "[dim]No active run.[/dim]"
        receipt_path = self._run_dir / "receipt.json"
        if not receipt_path.exists():
            return "[dim]receipt.json not found.[/dim]"
        try:
            from opencontext_core.workflow.phase_result import PhaseResultEnvelope

            env = PhaseResultEnvelope.model_validate_json(receipt_path.read_text(encoding="utf-8"))
            status_color = "green" if env.status in ("passed", "success") else "red"
            lines = [
                f"[bold]Run:[/] {env.run_id}",
                f"[bold]Change:[/] {env.change_id}",
                f"[bold]Phase:[/] {env.phase}",
                f"[bold]Status:[/] [{status_color}]{env.status}[/{status_color}]",
                f"[bold]Duration:[/] {env.duration_s:.2f}s",
            ]
            if env.missing_artifacts:
                lines.append("")
                lines.append("[bold][red]Missing Artifacts:[/red][/bold]")
                lines.extend(f"  [red]- {a}[/red]" for a in env.missing_artifacts)
            if env.risks:
                lines.append("")
                lines.append("[bold][yellow]Risks:[/yellow][/bold]")
                lines.extend(f"  [yellow]- {r}[/yellow]" for r in env.risks)
            if env.next_recommended:
                lines.append(f"\n[bold]Next:[/] {env.next_recommended}")
            return "\n".join(lines)
        except Exception as exc:
            return f"[red]Error reading receipt: {exc}[/red]"

    def action_dismiss(self) -> None:
        self.app.pop_screen()
