"""commit-013 screens 1-12: import + factory smoke, parametrized.

Consolidates the twelve per-screen ``test_sN_*_present.py`` files into a
single parametrized module. Each screen module must import cleanly and its
``screen_factory`` must return a ``DataScreen``.
"""

from __future__ import annotations

import pytest
from opencontext_studio.tui._test_helpers import (
    assert_factory_returns_screen,
    assert_module_importable,
)

SCREEN_MODULES = [
    "opencontext_studio.tui.s1_dashboard",
    "opencontext_studio.tui.s2_workflows",
    "opencontext_studio.tui.s3_decision_log",
    "opencontext_studio.tui.s4_brain_scheduler",
    "opencontext_studio.tui.s5_capability_graph",
    "opencontext_studio.tui.s6_context_budget",
    "opencontext_studio.tui.s7_cache_metrics",
    "opencontext_studio.tui.s8_learning_candidates",
    "opencontext_studio.tui.s9_plugin_panel",
    "opencontext_studio.tui.s10_provider_health",
    "opencontext_studio.tui.s11_benchmark_status",
    "opencontext_studio.tui.s12_settings",
]


@pytest.mark.parametrize("module", SCREEN_MODULES)
def test_screen_module_importable(module: str) -> None:
    assert_module_importable(module)


@pytest.mark.parametrize("module", SCREEN_MODULES)
def test_screen_factory_returns_textual_screen(module: str) -> None:
    assert_factory_returns_screen(module)
