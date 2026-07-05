"""commit-013 screen 8/12: learning_candidates.

Renders pending candidates, evidence refs, promotion status. Source:
``MemoryStore.candidates()`` + ``DecisionLog.promotion_decisions``.
"""

from __future__ import annotations

from opencontext_studio.tui.base import DataScreen
from opencontext_studio.tui.data import get_state


def screen_factory() -> DataScreen:
    state = get_state()
    body = (
        f"candidates={','.join(state['candidates'])} "
        f"evidence={','.join(state['evidence'])} "
        f"promotion_status={state['promotion_status']}"
    )
    return DataScreen(body, id="learning_candidates")


__all__ = ["screen_factory"]
