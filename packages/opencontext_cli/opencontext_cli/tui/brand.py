"""Shared brand chrome for the Textual TUI — one logo, one palette, every screen.

The palette mirrors ``opencontext_core.dx.console_styles`` so the TUI, the rich
CLI output and the rendered README demos all read as the same product.
"""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Static

from opencontext_core.dx.brand_mark import README_LOGO_TERMINAL
from opencontext_core.dx.brand_state import RuntimeBrandState, gather_runtime_brand_state

# House palette (kept in sync with opencontext_core.dx.console_styles).
PRIMARY = "#00C9A7"  # teal
SECONDARY = "#00A8E8"  # blue
ACCENT = "#845EC2"  # purple
SUCCESS = "#00C9A7"
WARNING = "#FFC75F"
ERROR = "#FF6F91"
DIM = "#6C757D"
BG = "#0B0F14"
PANEL = "#11161D"
FG = "#E6EDF3"


def render_brand_header(state: RuntimeBrandState) -> str:
    """Render README logo + useful runtime state."""
    logo = README_LOGO_TERMINAL
    width = max(len(line) for line in logo)
    cell = [line.ljust(width) for line in logo]
    project_line = (
        f"Project: {state.project_name} · {state.project_status}"
        if state.files == 0 and state.symbols == 0
        else (
            f"Project: {state.project_name} · {state.project_status} · "
            f"{state.files} files · {state.symbols} symbols"
        )
    )
    return "\n".join(
        [
            f"[bold {PRIMARY}]{cell[0]}[/]  [bold]OpenContext Runtime[/]",
            f"[{DIM}]{cell[1]}[/]  {project_line}",
            (
                f"[bold {SECONDARY}]{cell[2]}[/]  KG: {state.kg_status} · "
                f"Memory: {state.memory_backend} · Flow: {state.flow_mode}"
            ),
            (
                f"[{DIM}]{cell[3]}[/]  Run: {state.run_label} · "
                f"phase: {state.phase_label} · next: {state.next_label}"
            ),
            f"[bold {ACCENT}]{cell[4]}[/]",
        ]
    )


class BrandBar(Static):
    """The OpenContext logo + tagline shown at the top of every screen."""

    DEFAULT_CSS = """
    BrandBar {
        height: auto;
        padding: 1 2 1 2;
        background: $background;
        color: $foreground;
        border-bottom: solid $primary 30%;
    }
    """

    def __init__(self, root: str | Path = ".") -> None:
        super().__init__(render_brand_header(gather_runtime_brand_state(root)), markup=True)
