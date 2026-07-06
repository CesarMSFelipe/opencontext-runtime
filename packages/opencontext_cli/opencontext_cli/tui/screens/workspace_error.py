"""WorkspaceErrorScreen — readable no-workspace error instead of a traceback."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static

from opencontext_cli.tui.brand import DIM, ERROR


class WorkspaceErrorScreen(Screen[None]):
    """Shown when the TUI is opened outside an OpenContext workspace."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape,q", "quit_tui", "Quit"),
    ]

    DEFAULT_CSS = """
    WorkspaceErrorScreen { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #workspace-error { height: 1fr; }
    """

    def __init__(self, root: Path | str = ".") -> None:
        super().__init__()
        self._root = Path(root)

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold {ERROR}]No OpenContext workspace found[/]\n\n"
            f"No opencontext.yaml at or above:\n  {escape(str(self._root))}\n\n"
            "Create a workspace with:\n"
            "  opencontext init\n\n"
            "Or open an existing one:\n"
            "  opencontext tui <path>\n\n"
            f"[{DIM}]Press q to quit.[/]",
            id="workspace-error",
            markup=True,
        )
        yield Footer()

    def action_quit_tui(self) -> None:
        self.app.exit()
