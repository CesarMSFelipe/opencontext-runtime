"""REQ-plugin-v1-002: 7-state lifecycle + illegal transition."""

from __future__ import annotations

import pytest

from opencontext_core.plugins.v2.lifecycle import (
    IllegalTransitionError,
    PluginState,
    PluginStateMachine,
)


def test_REQ_plugin_v1_002_happy_path() -> None:
    sm = PluginStateMachine()
    sm.transition(PluginState.install)
    sm.transition(PluginState.validate)
    sm.transition(PluginState.enable)
    sm.transition(PluginState.disable)
    sm.transition(PluginState.remove)
    assert sm.current == PluginState.remove


def test_REQ_plugin_v1_002_illegal_transition() -> None:
    sm = PluginStateMachine()
    sm.transition(PluginState.install)
    with pytest.raises(IllegalTransitionError):
        sm.transition(PluginState.enable)  # install -> enable illegal


def test_seven_states_present() -> None:
    assert {s.name for s in PluginState} >= {
        "install",
        "validate",
        "enable",
        "upgrade",
        "disable",
        "remove",
        "migrate",
    }
