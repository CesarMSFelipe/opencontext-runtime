"""commit-013: shared Screen base for the 12 TUI screens.

Each screen renders its share of the public state as a textual
``Static`` widget. The widget's ``renderable`` is the single string the
tests assert on (Amendment-2: no empty/placeholder content).
"""

from __future__ import annotations

from textual.containers import Container
from textual.widgets import Static


class DataScreen(Container):
    """Container that renders *body* as a single ``Static`` widget.

    Subclasses set ``body`` in :meth:`__init__`. The textual App
    composes the screen; the test inspects the contained ``Static``
    widget to assert on the rendered string.
    """

    DEFAULT_CSS = ""

    def __init__(self, body: str, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._body = body
        self._static: Static | None = None

    def compose(self):  # type: ignore[no-untyped-def]
        self._static = Static(self._body)
        yield self._static

    @property
    def rendered(self) -> str:
        """The text the Static widget will paint."""
        return self._body


__all__ = ["DataScreen"]
