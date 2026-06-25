"""LearningInbox — lists pending evolution proposals from the learning engine."""

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


class LearningInbox(Screen):  # type: ignore[misc,valid-type]
    """Lists pending evolution proposals from the learning engine."""

    BINDINGS: ClassVar[list] = [
        Binding("escape,q", "dismiss", "Back"),
    ]

    DEFAULT_CSS = """
    LearningInbox { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #proposals-content { height: 1fr; }
    """

    def __init__(self, project_root: Path | None = None) -> None:
        super().__init__()
        self._project_root = project_root or Path.cwd()

    def compose(self) -> ComposeResult:
        yield Static("", id="proposals-content", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        content = self.query_one("#proposals-content", Static)
        content.update(self._load_proposals())

    def _load_proposals(self) -> str:
        try:
            from opencontext_core.learning.evolution_store import EvolutionStore

            store = EvolutionStore(project_root=self._project_root)
            proposals = store.list_proposals()
            if not proposals:
                return "[dim]No evolution proposals.[/dim]"
            lines = ["[bold]Evolution Proposals:[/]", ""]
            for p in proposals:
                approved = getattr(p, "approved", False)
                status = "[green]approved[/green]" if approved else "[yellow]pending[/yellow]"
                title = getattr(p, "title", None) or getattr(p, "kind", str(p))
                lines.append(f"  [{status}] [bold]{p.id}[/bold]: {title}")
            return "\n".join(lines)
        except Exception as exc:
            return f"[red]Error loading proposals: {exc}[/red]"

    def action_dismiss(self) -> None:
        self.app.pop_screen()
