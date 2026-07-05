"""commit-013 screen 11/12: benchmark_status.

Renders the 12 release-gate suite statuses. Source: the single SoT at
``benchmarks/v2/gates.py`` (no duplicated gate list).
"""

from __future__ import annotations

from opencontext_studio.tui.base import DataScreen
from opencontext_studio.tui.data import get_state


def screen_factory() -> DataScreen:
    state = get_state()
    suites = state["suites"]
    body = " ".join(f"{name}={status}" for name, status in sorted(suites.items()))
    return DataScreen(body, id="benchmark_status")


__all__ = ["screen_factory"]
