"""OpenContext brand styles and console utilities.

Provides consistent colors, styles, and formatting across the CLI.
Uses rich for colored output, tables, panels, and progress bars.
"""

from __future__ import annotations

from typing import Any

from opencontext_core.dx.brand_mark import README_LOGO_TERMINAL

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.style import Style
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Brand colors
BRAND_PRIMARY = "#00C9A7"  # Teal
BRAND_SECONDARY = "#00A8E8"  # Blue
BRAND_ACCENT = "#845EC2"  # Purple
BRAND_SUCCESS = "#00C9A7"
BRAND_WARNING = "#FFC75F"
BRAND_ERROR = "#FF6F91"
BRAND_INFO = "#00A8E8"
BRAND_DIM = "#6C757D"

# Styles (only if rich is available)
if RICH_AVAILABLE:
    STYLE_SUCCESS: Style = Style(color=BRAND_SUCCESS, bold=True)
    STYLE_ERROR: Style = Style(color=BRAND_ERROR, bold=True)
    STYLE_WARNING: Style = Style(color=BRAND_WARNING, bold=True)
    STYLE_INFO: Style = Style(color=BRAND_INFO, bold=True)
    STYLE_DIM: Style = Style(color=BRAND_DIM)
    STYLE_PRIMARY: Style = Style(color=BRAND_PRIMARY, bold=True)
    STYLE_SECONDARY: Style = Style(color=BRAND_SECONDARY)
else:
    STYLE_SUCCESS = None  # type: ignore[assignment]
    STYLE_ERROR = None  # type: ignore[assignment]
    STYLE_WARNING = None  # type: ignore[assignment]
    STYLE_INFO = None  # type: ignore[assignment]
    STYLE_DIM = None  # type: ignore[assignment]
    STYLE_PRIMARY = None  # type: ignore[assignment]
    STYLE_SECONDARY = None  # type: ignore[assignment]


# ── OpenContext logo — knowledge-graph motif in brand colors ──────────────────
# Glyph source lives in `opencontext_core.dx.brand_mark` (single source of truth
# shared with the TUI). Wrap each line with rich markup so the terminal renders
# the same icon everywhere — no marketing strings, no invented alternate logos.
_RICH_LOGO: list[str] = [
    f"[bold {BRAND_PRIMARY}]{README_LOGO_TERMINAL[0]}[/]",
    f"[{BRAND_DIM}]{README_LOGO_TERMINAL[1]}[/]",
    f"[bold {BRAND_SECONDARY}]{README_LOGO_TERMINAL[2]}[/]",
    f"[{BRAND_DIM}]{README_LOGO_TERMINAL[3]}[/]",
    f"[bold {BRAND_ACCENT}]{README_LOGO_TERMINAL[4]}[/]",
]


_QUIET_FALSEY = frozenset({"", "0", "false", "no", "off"})


def quiet_mode_active() -> bool:
    """True when ``--quiet`` / ``OPENCONTEXT_QUIET`` is in effect (CLI_CONTRACT).

    Quiet mode suppresses human-facing progress/status text on stdout; error
    surfaces (stderr-bound consoles) keep printing.
    """
    import os

    return os.environ.get("OPENCONTEXT_QUIET", "").strip().lower() not in _QUIET_FALSEY


class BrandConsole:
    """Console wrapper with brand styling."""

    def __init__(self) -> None:
        self._console = Console() if RICH_AVAILABLE else None

    def _suppressed(self) -> bool:
        """Quiet mode silences stdout-bound chrome; stderr consoles still emit."""
        if not quiet_mode_active():
            return False
        if self._console is not None and getattr(self._console, "stderr", False):
            return False
        return True

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to the underlying rich console."""
        if self._console and hasattr(self._console, name):
            return getattr(self._console, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __enter__(self) -> BrandConsole:
        if self._console:
            self._console.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._console:
            self._console.__exit__(exc_type, exc_val, exc_tb)

    @property
    def available(self) -> bool:
        return self._console is not None

    def print(self, *args: Any, **kwargs: Any) -> None:
        """Print with rich if available."""
        if self._suppressed():
            return
        if self._console:
            self._console.print(*args, **kwargs)
        else:
            print(*args, **kwargs)

    def success(self, message: str) -> None:
        self.print(f"[bold {BRAND_SUCCESS}]✓[/] {message}")

    def error(self, message: str) -> None:
        self.print(f"[bold {BRAND_ERROR}]✗[/] {message}")

    def warning(self, message: str) -> None:
        self.print(f"[bold {BRAND_WARNING}]⚠[/] {message}")

    def info(self, message: str) -> None:
        self.print(f"[bold {BRAND_INFO}]i[/] {message}")

    def dim(self, message: str) -> None:
        self.print(f"[{BRAND_DIM}]{message}[/{BRAND_DIM}]")

    def header(self, title: str = "") -> None:
        """Print a branded header — the logo plus (optionally) a titled panel — so
        every command surface (install, status, doctor, uninstall…) carries the
        same brand chrome as the interactive menus, not a bare title rule."""
        if self._suppressed():
            return
        if self._console:
            for line in _RICH_LOGO:
                self._console.print(line)
            if title:
                self._console.print(
                    Panel(
                        Text(title, justify="center", style=f"bold {BRAND_PRIMARY}"),
                        border_style=BRAND_PRIMARY,
                        padding=(0, 2),
                    )
                )
        else:
            for line in _RICH_LOGO:
                print(line)
            if title:
                print(f"\n{'=' * 60}")
                print(f"  {title}")
                print(f"{'=' * 60}\n")

    def section(self, title: str) -> None:
        """Print a section header."""
        self.print(f"\n[bold {BRAND_PRIMARY}]{title}[/]")
        self.print(f"[{BRAND_DIM}]{'─' * 40}[/]")

    def table(self, title: str, columns: list[str], rows: list[list[str]]) -> Table | None:
        """Create a styled table."""
        if self._suppressed():
            return None
        if not self._console:
            # Fallback: simple text table
            print(f"\n{title}:")
            for row in rows:
                print("  " + " | ".join(row))
            return None

        table = Table(title=title, title_style=f"bold {BRAND_PRIMARY}")
        for col in columns:
            table.add_column(col, style=BRAND_SECONDARY)
        for row in rows:
            table.add_row(*row)
        self._console.print(table)
        return table

    def progress(self, description: str = "Working...") -> Any:
        """Create a progress context manager."""
        if self._suppressed():
            return _NoOpProgress()
        if not self._console:
            print(description)
            return _NoOpProgress()

        return Progress(
            SpinnerColumn(style=BRAND_PRIMARY),
            TextColumn(f"[bold {BRAND_PRIMARY}]{description}[/]"),
            console=self._console,
        )

    def status(self, message: str, *, spinner: str = "dots") -> Any:
        """Brand-styled spinner context manager.

        Single chrome for every long-running CLI step: brand-primary message and
        spinner. Falls back to a plain print + no-op context manager when rich
        is unavailable, so ``with console.status(...)`` never crashes.
        """
        if self._suppressed():
            return _NoOpStatus()
        if not self._console:
            print(message)
            return _NoOpStatus()
        return self._console.status(
            f"[bold {BRAND_PRIMARY}]{message}[/]",
            spinner=spinner,
            spinner_style=BRAND_PRIMARY,
        )

    def panel(
        self,
        content: str,
        title: str | None = None,
        *,
        style: str = "info",
        fit: bool = False,
    ) -> None:
        """Print content in a brand-bordered panel.

        ``style`` picks the border color from the brand palette: ``info``
        (default), ``success``, ``warning``, or ``error``. ``fit=True`` sizes
        the panel to its content (compact result banners) instead of full width.
        """
        if self._suppressed():
            return
        border = {
            "info": BRAND_SECONDARY,
            "success": BRAND_SUCCESS,
            "warning": BRAND_WARNING,
            "error": BRAND_ERROR,
        }.get(style, BRAND_SECONDARY)
        if self._console:
            if fit:
                rendered = Panel.fit(content, title=title, border_style=border, padding=(0, 2))
            else:
                rendered = Panel(content, title=title, border_style=border, padding=(1, 2))
            self._console.print(rendered)
        else:
            if title:
                print(f"\n{title}:")
            print(content)


class _NoOpStatus:
    """No-op status context manager for when rich is not available."""

    def __enter__(self) -> _NoOpStatus:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def update(self, *args: Any, **kwargs: Any) -> None:
        pass


class _NoOpProgress:
    """No-op progress for when rich is not available."""

    def __enter__(self) -> _NoOpProgress:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def add_task(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def update(self, *args: Any, **kwargs: Any) -> None:
        pass


# Global console instance
console = BrandConsole()


def success(message: str) -> None:
    """Print success message."""
    console.success(message)


def error(message: str) -> None:
    """Print error message."""
    console.error(message)


def warning(message: str) -> None:
    """Print warning message."""
    console.warning(message)


def info(message: str) -> None:
    """Print info message."""
    console.info(message)


def header(title: str) -> None:
    """Print branded header."""
    console.header(title)


def section(title: str) -> None:
    """Print section header."""
    console.section(title)


def show_logo() -> list[str]:
    """Print the full OpenContext logo and return the rendered lines.

    Glyphs are sourced from ``opencontext_core.dx.brand_mark`` (the same
    single-source tuple the TUI uses) so README, TUI and CLI stay in lockstep.
    Renders the full 5-line mark. Existing call sites that treat ``show_logo``
    as a side-effecting print keep working because the lines are still echoed
    to the brand console.
    """
    for line in _RICH_LOGO:
        console.print(line)
    return list(_RICH_LOGO)
