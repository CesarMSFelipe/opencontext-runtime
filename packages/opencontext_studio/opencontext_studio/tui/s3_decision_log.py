"""commit-013 screen 3/12: decision_log.

Renders decision_id / rationale / alternatives / cost / timestamp.
Source: ``decision_log/recorder`` read API + ``Run.decisions[]``.
"""

from __future__ import annotations

from opencontext_studio.tui.base import DataScreen
from opencontext_studio.tui.data import get_state


def screen_factory() -> DataScreen:
    state = get_state()
    body = (
        f"decision_id={state['decision_id']} "
        f"rationale={state['rationale']} "
        f"alternatives={','.join(state['alternatives_considered'])} "
        f"cost={state['cost']} "
        f"timestamp={state['timestamp']}"
    )
    return DataScreen(body, id="decision_log")


__all__ = ["screen_factory"]
