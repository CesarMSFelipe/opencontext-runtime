"""commit-013: smoke test — all 12 screens render headless under 30s.

The smoke test composes every screen in a single Textual ``App``,
headless, and asserts the wall-clock budget. It also flips the
``studio-control-plane`` compat flag default to ``True`` so the
control plane is live by default once the v2 surface ships.
"""

from __future__ import annotations

import asyncio
import time

from opencontext_studio.tui.screens import SCREENS


def test_total_under_30s() -> None:
    """Compose all 12 screens and assert the wall-clock budget."""
    from textual.app import App

    class _AllScreensApp(App):
        def compose(self):  # type: ignore[no-untyped-def]
            for factory in SCREENS.values():
                yield factory()

    started = time.monotonic()

    async def _drive() -> None:
        app = _AllScreensApp()
        async with app.run_test(headless=True) as pilot:
            await pilot.pause(0.05)

    asyncio.run(_drive())
    elapsed = time.monotonic() - started
    assert elapsed < 30.0, f"12 screens took {elapsed:.2f}s (>30s budget)"


def test_studio_control_plane_flag_is_on() -> None:
    from opencontext_core.compat import is_migrated_flag

    # The compat flag flips to True at this commit (013m).
    assert is_migrated_flag("studio-control-plane") is True


def test_no_screen_renders_empty() -> None:
    """Consolidated gate: every screen has a non-empty rendered body."""
    for name, factory in SCREENS.items():
        screen = factory()
        body = screen.rendered
        assert body and body.strip(), f"{name} rendered an empty body"
