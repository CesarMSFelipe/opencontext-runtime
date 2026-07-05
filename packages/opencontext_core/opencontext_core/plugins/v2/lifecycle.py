"""PR-015 PluginStateMachine — 7-state lifecycle (CONV2 #13)."""

from __future__ import annotations

from enum import StrEnum


class IllegalTransitionError(Exception):
    """A state transition that is not permitted by the lifecycle FSM."""


class PluginState(StrEnum):
    install = "install"
    validate = "validate"
    enable = "enable"
    upgrade = "upgrade"
    disable = "disable"
    remove = "remove"
    migrate = "migrate"


# Allowed transitions. Each state maps to the legal next states.
_TRANSITIONS: dict[PluginState, frozenset[PluginState]] = {
    PluginState.install: frozenset({PluginState.validate, PluginState.remove}),
    PluginState.validate: frozenset({PluginState.enable, PluginState.remove}),
    PluginState.enable: frozenset({PluginState.upgrade, PluginState.disable, PluginState.remove}),
    PluginState.upgrade: frozenset({PluginState.enable, PluginState.disable, PluginState.remove}),
    PluginState.disable: frozenset({PluginState.enable, PluginState.remove, PluginState.migrate}),
    PluginState.remove: frozenset({PluginState.install}),
    PluginState.migrate: frozenset({PluginState.install, PluginState.remove}),
}


class PluginStateMachine:
    """7-state lifecycle FSM for a single plugin."""

    def __init__(self) -> None:
        self.current: PluginState | None = None

    def transition(self, target: PluginState) -> PluginState:
        if self.current is None:
            # First transition must be ``install``.
            if target != PluginState.install:
                raise IllegalTransitionError(f"initial transition must be install, got {target!r}")
            self.current = target
            return target
        allowed = _TRANSITIONS[self.current]
        if target not in allowed:
            raise IllegalTransitionError(
                f"cannot transition {self.current!r} -> {target!r}; "
                f"allowed: {sorted(s.value for s in allowed)}"
            )
        self.current = target
        return target
