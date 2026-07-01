"""commit-013 screen 12/12: settings.

Renders profile, ``opencontext.yaml`` path, current session scope,
key toggles. Source: ``ConfigStore.current()`` + ``paths.resolve_*``.
"""

from __future__ import annotations

from opencontext_studio.tui.base import DataScreen
from opencontext_studio.tui.data import get_state


def screen_factory() -> DataScreen:
    state = get_state()
    toggles = ",".join(f"{k}={v}" for k, v in state["toggles"].items())
    body = (
        f"profile={state['profile']} "
        f"config_path={state['config_path']} "
        f"scope={state['scope']} "
        f"toggles={toggles}"
    )
    return DataScreen(body, id="settings")


__all__ = ["screen_factory"]
