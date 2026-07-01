"""commit-013 screen 4/12: brain_scheduler.

Renders workflow / persona / skill / context decisions with rationale.
Source: ``runtime/brain_scheduler`` decision log.
"""

from __future__ import annotations

from opencontext_studio.tui.base import DataScreen
from opencontext_studio.tui.data import get_state


def screen_factory() -> DataScreen:
    state = get_state()
    body = (
        f"workflow_decision={state['workflow_decision']} "
        f"persona_decision={state['persona_decision']} "
        f"skill_decision={state['skill_decision']} "
        f"context_decision={state['context_decision']}"
    )
    return DataScreen(body, id="brain_scheduler")


__all__ = ["screen_factory"]
