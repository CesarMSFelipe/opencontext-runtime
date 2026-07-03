"""Shared chrome for interactive wizard steps — one frame, every wizard.

Interactive flows (install, init/onboarding, setup, config wizard, plugin
picker, uninstall scope selector) render the same "aspect" as the config TUI:
the compact brand logo with a live status line, a "Step N/M" progress trail,
and a per-step detail card in the TUI info-pane format::

    Current: ...
    Effect: ...
    Recommended: ...
    Risk / note: ...
    CLI: ...

``WizardStep`` carries the card content; ``render_frame`` clears the screen and
prints the frame. On a non-TTY the frame renders nothing at all — prompts are
skipped there anyway, so piped/CI output stays clean.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path

from opencontext_core.dx.brand_mark import README_LOGO_TERMINAL_COMPACT
from opencontext_core.dx.console_styles import (
    BRAND_DIM,
    BRAND_PRIMARY,
    BRAND_SECONDARY,
    console,
)

__all__ = ["WizardStep", "frame_lines", "render_frame", "wizard_status_line"]


@dataclass(frozen=True)
class WizardStep:
    """One wizard step's title + info-pane detail card.

    Field order mirrors the config TUI info pane: what the setting currently
    is, what choosing it does, what we recommend, what to watch out for, and
    the non-interactive CLI equivalent.
    """

    title: str
    current: str = ""
    effect: str = ""
    recommended: str = ""
    risk: str = ""
    cli: str = ""

    def detail_pairs(self) -> list[tuple[str, str]]:
        """(label, value) pairs in info-pane order; empty values are skipped."""
        pairs = [
            ("Current", self.current),
            ("Effect", self.effect),
            ("Recommended", self.recommended),
            ("Risk / note", self.risk),
            ("CLI", self.cli),
        ]
        return [(label, value) for label, value in pairs if value]

    def with_current(self, current: str) -> WizardStep:
        """Copy of this step with the live ``Current:`` value filled in."""
        return replace(self, current=current)


def _is_tty() -> bool:
    return bool(getattr(sys.stdin, "isatty", lambda: False)()) and bool(
        getattr(sys.stdout, "isatty", lambda: False)()
    )


def wizard_status_line(root: str | Path = ".") -> str:
    """Live one-line status matching the TUI BrandBar (project · KG · memory · flow)."""
    try:
        from opencontext_core.dx.brand_state import gather_runtime_brand_state

        state = gather_runtime_brand_state(root)
    except Exception:
        return ""
    return " · ".join(
        [
            f"{state.project_name} · {state.project_status}",
            f"KG: {state.kg_status}",
            f"Memory: {state.memory_backend}",
            f"Flow: {state.flow_mode}",
        ]
    )


def frame_lines(step_index: int, total: int, step: WizardStep, status_line: str = "") -> list[str]:
    """Build the frame as rich-markup lines (pure — no printing, no TTY check).

    Layout: compact logo with the status line beside it, a bold step title with
    progress dots and ``Step N/M``, then the detail card (dim labels, plain
    values) — visually the same info pane the config TUI shows.
    """
    logo = README_LOGO_TERMINAL_COMPACT
    width = max(len(line) for line in logo)
    cell = [line.ljust(width) for line in logo]
    lines = [
        f"[bold {BRAND_PRIMARY}]{cell[0]}[/]  [bold]OpenContext[/]",
        f"[{BRAND_DIM}]{cell[1]}[/]  [{BRAND_DIM}]{status_line}[/]",
        f"[bold {BRAND_SECONDARY}]{cell[2]}[/]",
        "",
    ]
    dots = "  ".join(
        f"[bold {BRAND_PRIMARY}]●[/]" if i <= step_index else f"[{BRAND_DIM}]○[/]"
        for i in range(1, total + 1)
    )
    lines.append(f"  [bold]{step.title}[/]   {dots}   [{BRAND_DIM}]Step {step_index}/{total}[/]")
    card = step.detail_pairs()
    if card:
        lines.append("")
        lines.extend(f"  [{BRAND_DIM}]{label}:[/] {value}" for label, value in card)
    lines.append("")
    return lines


def render_frame(
    step_index: int,
    total: int,
    step: WizardStep,
    status_line: str | None = None,
    *,
    root: str | Path = ".",
    clear: bool = True,
) -> bool:
    """Clear the screen and render the shared wizard frame.

    Returns ``True`` when the frame was rendered, ``False`` on a non-TTY
    (nothing is printed — the interactive steps are skipped there anyway).
    ``status_line=None`` computes the live status from *root*; pass a
    precomputed string to avoid re-gathering state on every step.
    """
    if not _is_tty():
        return False
    if clear:
        try:
            console.clear()
        except Exception:
            pass
    line = wizard_status_line(root) if status_line is None else status_line
    for rendered in frame_lines(step_index, total, step, line):
        console.print(rendered)
    return True
