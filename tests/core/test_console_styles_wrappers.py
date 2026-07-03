"""Contract tests for the BrandConsole chrome wrappers (status/panel).

Every user-facing command routes spinners and panels through these wrappers so
the whole CLI carries one brand palette. Locked down here: the context-manager
shape (so ``with console.status(...)`` never crashes), the panel style variants,
and the no-rich fallbacks that keep bare terminals working.
"""

from __future__ import annotations

import io

from rich.console import Console

from opencontext_core.dx.console_styles import BrandConsole


def _capture_console() -> tuple[BrandConsole, io.StringIO]:
    buf = io.StringIO()
    bc = BrandConsole()
    bc._console = Console(file=buf, force_terminal=False, width=100)
    return bc, buf


# ── status (spinner) ─────────────────────────────────────────────────────


def test_status_is_a_context_manager() -> None:
    bc, _ = _capture_console()
    with bc.status("Working..."):
        pass  # must not raise


def test_status_accepts_spinner_kwarg() -> None:
    # Existing call sites pass spinner="dots"; the wrapper must keep accepting it.
    bc, _ = _capture_console()
    with bc.status("Working...", spinner="dots"):
        pass


def test_status_without_rich_falls_back_to_print(capsys) -> None:
    bc = BrandConsole()
    bc._console = None
    with bc.status("Working..."):
        pass
    assert "Working..." in capsys.readouterr().out


# ── panel variants ───────────────────────────────────────────────────────


def test_panel_renders_content_and_title() -> None:
    bc, buf = _capture_console()
    bc.panel("hello world", title="Greeting")
    out = buf.getvalue()
    assert "hello world" in out
    assert "Greeting" in out


def test_panel_supports_style_variants_and_fit() -> None:
    bc, buf = _capture_console()
    for style in ("info", "success", "warning", "error", "unknown"):
        bc.panel("body", title="T", style=style, fit=True)
    assert buf.getvalue().count("body") == 5


def test_panel_without_rich_falls_back_to_print(capsys) -> None:
    bc = BrandConsole()
    bc._console = None
    bc.panel("plain body", title="Plain", style="success", fit=True)
    out = capsys.readouterr().out
    assert "plain body" in out
    assert "Plain" in out
