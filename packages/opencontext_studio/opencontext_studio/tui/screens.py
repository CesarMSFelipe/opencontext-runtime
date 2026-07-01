"""commit-013: registry of all 12 TUI screens (single SoT for the gate test)."""

from __future__ import annotations

from collections.abc import Callable

from opencontext_studio.tui.s1_dashboard import screen_factory as dashboard
from opencontext_studio.tui.s2_workflows import screen_factory as workflows
from opencontext_studio.tui.s3_decision_log import screen_factory as decision_log
from opencontext_studio.tui.s4_brain_scheduler import screen_factory as brain_scheduler
from opencontext_studio.tui.s5_capability_graph import screen_factory as capability_graph
from opencontext_studio.tui.s6_context_budget import screen_factory as context_budget
from opencontext_studio.tui.s7_cache_metrics import screen_factory as cache_metrics
from opencontext_studio.tui.s8_learning_candidates import screen_factory as learning_candidates
from opencontext_studio.tui.s9_plugin_panel import screen_factory as plugin_panel
from opencontext_studio.tui.s10_provider_health import screen_factory as provider_health
from opencontext_studio.tui.s11_benchmark_status import screen_factory as benchmark_status
from opencontext_studio.tui.s12_settings import screen_factory as settings

SCREENS: dict[str, Callable[[], object]] = {
    "dashboard": dashboard,
    "workflows": workflows,
    "decision_log": decision_log,
    "brain_scheduler": brain_scheduler,
    "capability_graph": capability_graph,
    "context_budget": context_budget,
    "cache_metrics": cache_metrics,
    "learning_candidates": learning_candidates,
    "plugin_panel": plugin_panel,
    "provider_health": provider_health,
    "benchmark_status": benchmark_status,
    "settings": settings,
}


__all__ = ["SCREENS"]
