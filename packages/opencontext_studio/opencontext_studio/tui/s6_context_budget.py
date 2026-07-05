"""commit-013 screen 6/12: context_budget.

Renders used/available tokens, included_refs, omitted_refs. Source:
latest ``ContextReceipt`` (Amendment A5 deep-evidence shape).
"""

from __future__ import annotations

from opencontext_studio.tui.base import DataScreen
from opencontext_studio.tui.data import get_state


def screen_factory() -> DataScreen:
    state = get_state()
    body = (
        f"used_tokens={state['used_tokens']} "
        f"available_tokens={state['available_tokens']} "
        f"included_refs={state['included_refs']} "
        f"omitted_refs={state['omitted_refs']}"
    )
    return DataScreen(body, id="context_budget")


__all__ = ["screen_factory"]
