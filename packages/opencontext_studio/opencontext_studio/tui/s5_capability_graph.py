"""commit-013 screen 5/12: capability_graph.

Renders available / missing / degraded capabilities + install_hint per
missing. Source: ``CapabilityGraph.nodes`` from
``session/capability-graph.json``.
"""

from __future__ import annotations

from opencontext_studio.tui.base import DataScreen
from opencontext_studio.tui.data import get_state


def screen_factory() -> DataScreen:
    state = get_state()
    hint = ",".join(f"{k}={v}" for k, v in state["install_hint"].items())
    body = (
        f"available={','.join(state['available'])} "
        f"missing={','.join(state['missing'])} "
        f"degraded={','.join(state['degraded'])} "
        f"install_hint={hint}"
    )
    return DataScreen(body, id="capability_graph")


__all__ = ["screen_factory"]
