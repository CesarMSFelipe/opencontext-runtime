"""commit-013 screen 1/12: dashboard.

Renders project / session_id / run_id / gates / next_action from the
shared state. Source: ``RuntimeApi.status`` + ``RuntimeApi.next``.
"""

from __future__ import annotations

from opencontext_studio.tui.base import DataScreen
from opencontext_studio.tui.data import get_state


def screen_factory() -> DataScreen:
    state = get_state()
    body = (
        f"project={state['project']} "
        f"session_id={state['session_id']} "
        f"run_id={state['run_id']} "
        f"gates={state['gates']} "
        f"next_action={state['next_action']}"
    )
    return DataScreen(body, id="dashboard")


__all__ = ["screen_factory"]
