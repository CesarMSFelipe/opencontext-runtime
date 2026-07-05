"""commit-013 screen 9/12: plugin_panel.

Renders installed plugins, capabilities, policy check status. Source:
``PluginRegistry.installed()`` + ``PolicyGate.check(plugin_id)``.
"""

from __future__ import annotations

from opencontext_studio.tui.base import DataScreen
from opencontext_studio.tui.data import get_state


def screen_factory() -> DataScreen:
    state = get_state()
    caps = ";".join(f"{p}={','.join(c)}" for p, c in state["capabilities"].items())
    body = (
        f"installed={','.join(state['installed'])} "
        f"capabilities={caps} "
        f"policy_status={state['policy_status']}"
    )
    return DataScreen(body, id="plugin_panel")


__all__ = ["screen_factory"]
