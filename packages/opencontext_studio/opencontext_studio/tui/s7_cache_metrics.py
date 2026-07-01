"""commit-013 screen 7/12: cache_metrics.

Renders hit/miss/eviction counts and top keys. Source:
``ArtifactStore.metrics()`` (cache layer).
"""

from __future__ import annotations

from opencontext_studio.tui.base import DataScreen
from opencontext_studio.tui.data import get_state


def screen_factory() -> DataScreen:
    state = get_state()
    top = ",".join(f"{k}:{v}" for k, v in state["top_keys"])
    body = (
        f"hit_rate={state['hit_rate']} "
        f"miss_rate={state['miss_rate']} "
        f"evictions={state['evictions']} "
        f"top_keys={top}"
    )
    return DataScreen(body, id="cache_metrics")


__all__ = ["screen_factory"]
