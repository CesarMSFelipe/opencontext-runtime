"""commit-013: shared helper for the per-screen present tests.

Avoids copy-pasting the import/factory checks across 12 modules. Each
screen's test_XX_name_present.py imports the helpers here and supplies
its own module path + id.
"""

from __future__ import annotations

import importlib
from typing import Any

from opencontext_studio.tui.base import DataScreen


def assert_module_importable(module_path: str) -> Any:
    mod = importlib.import_module(module_path)
    assert hasattr(mod, "screen_factory"), f"{module_path} missing screen_factory"
    return mod


def assert_factory_returns_screen(module_path: str) -> DataScreen:
    mod = assert_module_importable(module_path)
    screen = mod.screen_factory()
    assert isinstance(screen, DataScreen), (
        f"{module_path}.screen_factory() did not return a DataScreen"
    )
    return screen


__all__ = ["assert_factory_returns_screen", "assert_module_importable"]
