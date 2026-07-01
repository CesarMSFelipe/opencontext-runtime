"""commit-013 screen 10/12: provider_health.

Renders provider, status, latency p50/p95, error rate. Source:
``ProviderRegistry.health()`` + ``RuntimeApi.get_health()``.
"""

from __future__ import annotations

from opencontext_studio.tui.base import DataScreen
from opencontext_studio.tui.data import get_state


def screen_factory() -> DataScreen:
    state = get_state()
    body = (
        f"provider={state['provider']} "
        f"status={state['status']} "
        f"latency_p50={state['latency_p50']} "
        f"latency_p95={state['latency_p95']} "
        f"error_rate={state['error_rate']}"
    )
    return DataScreen(body, id="provider_health")


__all__ = ["screen_factory"]
