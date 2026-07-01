"""commit-013 screen 2/12: workflows.

Renders chosen workflow / alternatives / confidence / risk from the
shared state. Source: ``runtime/workflow_selection`` decision log.
"""

from __future__ import annotations

from opencontext_studio.tui.base import DataScreen
from opencontext_studio.tui.data import get_state


def screen_factory() -> DataScreen:
    state = get_state()
    body = (
        f"workflow={state['workflow']} "
        f"alternatives={','.join(state['alternatives'])} "
        f"confidence={state['confidence']} "
        f"risk={state['risk']}"
    )
    return DataScreen(body, id="workflows")


__all__ = ["screen_factory"]
