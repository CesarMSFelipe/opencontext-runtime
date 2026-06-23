"""OpenContext brand styles and console utilities.

Provides consistent colors, styles, and formatting across the CLI.
Uses rich for colored output, tables, panels, and progress bars.
"""

from __future__ import annotations

from typing import Any

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
# Single source of truth so every menu, wizard and action screen renders the
# same icon. Full form on roomy terminals, compact (3-line) form otherwise.
LOGO = [
    "",
    f"  [bold {BRAND_PRIMARY}]◉[/][dim]──[/][bold {BRAND_SECONDARY}]◉[/][dim]──[/]"
    f"[bold {BRAND_ACCENT}]◉[/]    [bold white]OpenContext Runtime[/]",
    f"  [{BRAND_PRIMARY}]│[/]     [{BRAND_ACCENT}]│[/]    "
    "[dim]Context Engineering for AI Agents[/]",
    f"  [{BRAND_PRIMARY}]◉[/][dim]──[/][{BRAND_SECONDARY}]◉[/]  [{BRAND_ACCENT}]◉[/]",
    f"  [{BRAND_PRIMARY}]│[/]  [{BRAND_SECONDARY}]│[/]       "
    f"[bold {BRAND_PRIMARY}]*[/] [bold]87% token reduction[/]  "
    f"[{BRAND_SECONDARY}]*[/] SDD workflow",
    f"  [{BRAND_PRIMARY}]◉[/][dim]──[/][{BRAND_SECONDARY}]◉[/]       "
    f"[{BRAND_ACCENT}]*[/] MCP server  [{BRAND_PRIMARY}]*[/] 13+ agents  "
    f"[{BRAND_SECONDARY}]*[/] Zero secrets",
    "",
]

COMPACT_LOGO = [
    f"  [bold {BRAND_PRIMARY}]◉──◉[/]  [bold white]OpenContext Runtime[/]",
    f"  [{BRAND_PRIMARY}]│  │[/]  [dim]Context Engineering · 87% token reduction[/]",
    f"  [bold {BRAND_PRIMARY}]◉──◉[/]  [dim]SDD · MCP · 13+ agents · Zero secrets[/]",
]


class BrandConsole:
    """Console wrapper with brand styling."""

    def __init__(self) -> None:
        self._console = Console() if RICH_AVAILABLE else None

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

    def header(self, title: str) -> None:
        """Print a branded header panel."""
        if self._console:
            self._console.print(
                Panel(
                    Text(title, justify="center", style=f"bold {BRAND_PRIMARY}"),
                    border_style=BRAND_PRIMARY,
                    padding=(1, 2),
                )
            )
        else:
            print(f"\n{'=' * 60}")
            print(f"  {title}")
            print(f"{'=' * 60}\n")

    def section(self, title: str) -> None:
        """Print a section header."""
        self.print(f"\n[bold {BRAND_PRIMARY}]{title}[/]")
        self.print(f"[{BRAND_DIM}]{'─' * 40}[/]")

    def table(self, title: str, columns: list[str], rows: list[list[str]]) -> Table | None:
        """Create a styled table."""
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
        if not self._console:
            print(description)
            return _NoOpProgress()

        return Progress(
            SpinnerColumn(style=BRAND_PRIMARY),
            TextColumn(f"[bold {BRAND_PRIMARY}]{description}[/]"),
            console=self._console,
        )

    def panel(self, content: str, title: str | None = None) -> None:
        """Print content in a panel."""
        if self._console:
            self._console.print(
                Panel(content, title=title, border_style=BRAND_SECONDARY, padding=(1, 2))
            )
        else:
            if title:
                print(f"\n{title}:")
            print(content)


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


def show_logo(*, compact: bool = False) -> None:
    """Print the OpenContext logo. Falls back to the compact form on small
    terminals (or when ``compact=True``), so it fits any menu or action screen."""
    import shutil

    lines = COMPACT_LOGO
    if not compact:
        try:
            size = shutil.get_terminal_size()
            if size.columns >= 64 and size.lines >= len(LOGO) + 14:
                lines = LOGO
        except Exception:
            pass
    for line in lines:
        console.print(line)
