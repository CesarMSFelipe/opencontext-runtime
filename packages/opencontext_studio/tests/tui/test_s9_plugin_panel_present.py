"""commit-013 screen 9/12: plugin_panel present."""

from __future__ import annotations

from opencontext_studio.tui._test_helpers import (
    assert_factory_returns_screen,
    assert_module_importable,
)

MODULE = "opencontext_studio.tui.s9_plugin_panel"


def test_screen_module_importable() -> None:
    assert_module_importable(MODULE)


def test_screen_factory_returns_textual_screen() -> None:
    assert_factory_returns_screen(MODULE)
