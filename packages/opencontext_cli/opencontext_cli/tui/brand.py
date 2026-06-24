"""Shared brand chrome for the Textual TUI — one logo, one palette, every screen.

The palette mirrors ``opencontext_core.dx.console_styles`` so the TUI, the rich
CLI output and the rendered README demos all read as the same product.
"""

from __future__ import annotations

from textual.widgets import Static

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

# The knowledge-graph logo motif, as Textual console markup (3-line compact form).
LOGO_MARKUP = (
    f"[bold {PRIMARY}]◉──◉──◉[/]  [bold]OpenContext Runtime[/]\n"
    f"[{PRIMARY}]│     │[/]  [{DIM}]Context Engineering · 87% token reduction[/]\n"
    f"[bold {PRIMARY}]◉──◉  ◉[/]  [{DIM}]SDD · MCP · 13+ agents · Zero secrets[/]"
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

    def __init__(self) -> None:
        super().__init__(LOGO_MARKUP, markup=True)
