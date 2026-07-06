"""DoctorScreen — health + security checks grouped by area, run off-thread.

Reuses the existing doctor machinery (``opencontext_core.doctor.checks``);
checks run in a thread worker so the UI never blocks, with a visible loading
state until results land.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static

from opencontext_cli.tui.brand import ERROR, SUCCESS, WARNING, BrandBar

#: Details markers for checks that passed in a degraded state.
_WARN_MARKERS = ("unavailable", "no llm provider detected")

_BADGE_MARKUP = {
    "pass": f"[{SUCCESS}]✓ pass[/]",
    "warn": f"[{WARNING}]⚠ warn[/]",
    "fail": f"[{ERROR}]✗ fail[/]",
}


def badge_for(ok: bool, details: str) -> str:
    """``fail`` when the check failed; ``warn`` when it passed degraded."""
    if not ok:
        return "fail"
    lowered = details.lower()
    if any(marker in lowered for marker in _WARN_MARKERS):
        return "warn"
    return "pass"


def group_checks(checks: list[Any]) -> dict[str, list[Any]]:
    """Group checks by area (the name prefix before the first dot)."""
    groups: dict[str, list[Any]] = {}
    for check in checks:
        area = str(check.name).split(".", 1)[0]
        groups.setdefault(area, []).append(check)
    return groups


def run_checks(root: Path) -> list[Any]:
    """Run the baseline + security doctor checks for *root*."""
    from opencontext_core.config import find_config, load_config_or_defaults
    from opencontext_core.doctor.checks import run_doctor, run_security_doctor

    config = load_config_or_defaults(find_config(root))
    return [*run_doctor(config), *run_security_doctor(config)]


def render_doctor_report(root: Path) -> str:
    """Grouped pass/warn/fail report — the blocking part, run off-thread."""
    checks = run_checks(root)
    lines: list[str] = []
    for area, area_checks in group_checks(checks).items():
        lines.append(f"[bold]{escape(area)}[/]")
        for check in area_checks:
            badge = _BADGE_MARKUP[badge_for(check.ok, check.details)]
            lines.append(f"  {badge}  {escape(check.name)}  [dim]{escape(check.details)}[/dim]")
        lines.append("")
    return "\n".join(lines)


class DoctorScreen(Screen[None]):
    """Doctor diagnostics grouped by area with pass/warn/fail badges."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape,q", "dismiss", "Back"),
    ]

    DEFAULT_CSS = """
    DoctorScreen { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #doctor-content { height: 1fr; }
    """

    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self._root = root or Path(".")

    def compose(self) -> ComposeResult:
        yield BrandBar()
        yield Static("[bold]Doctor[/]\n[dim]Health and security checks[/]", markup=True)
        yield Static("[dim]Running doctor checks…[/dim]", id="doctor-content", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._content = self.query_one("#doctor-content", Static)
        self.run_worker(self._collect, thread=True)

    def _collect(self) -> None:
        try:
            text = render_doctor_report(self._root)
        except Exception as exc:  # a doctor failure must render, not crash
            text = f"[red]Doctor failed: {escape(str(exc))}[/red]"
        self.app.call_from_thread(self._content.update, text)

    def action_dismiss(self, result: Any = None) -> None:  # type: ignore[override]
        self.app.pop_screen()
