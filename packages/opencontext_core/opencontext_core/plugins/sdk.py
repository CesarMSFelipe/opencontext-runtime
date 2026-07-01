"""Plugin SDK — PR-015 manifest, registry, lifecycle SM, permission, conformance."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PluginState(str, Enum):
    REGISTERED = "registered"
    LOADED = "loaded"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


TRANSITIONS: dict[PluginState, set[PluginState]] = {
    PluginState.REGISTERED: {PluginState.LOADED},
    PluginState.LOADED: {PluginState.RUNNING, PluginState.STOPPED, PluginState.ERROR},
    PluginState.RUNNING: {PluginState.STOPPED, PluginState.ERROR},
    PluginState.STOPPED: {PluginState.RUNNING, PluginState.REGISTERED},
    PluginState.ERROR: {PluginState.STOPPED, PluginState.REGISTERED},
}


class PluginError(Exception):
    pass


@dataclass
class PluginManifest:
    name: str
    version: str
    endpoints: int = 0
    permissions: list[str] = field(default_factory=list)


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}
        self._states: dict[str, PluginState] = {}

    def register(self, manifest: PluginManifest) -> None:
        self._plugins[manifest.name] = manifest
        self._states[manifest.name] = PluginState.REGISTERED

    def transition(self, name: str, target: PluginState) -> None:
        current = self._states.get(name, PluginState.REGISTERED)
        allowed = TRANSITIONS.get(current, set())
        if target not in allowed:
            raise PluginError(f"Cannot transition {name} from {current.value} to {target.value}")
        self._states[name] = target

    def list(self) -> list[PluginManifest]:
        return list(self._plugins.values())


class PluginConformance:
    def check(self, manifest: PluginManifest) -> list[str]:
        issues: list[str] = []
        if not manifest.name:
            issues.append("missing name")
        if manifest.endpoints < 1:
            issues.append("no endpoints defined")
        return issues
