"""Plugin SDK — PR-015 manifest + registry + lifecycle + permission + conformance."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PluginState(str, Enum):
    REGISTERED = "registered"
    LOADED = "loaded"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class PluginManifest:
    name: str
    version: str
    endpoints: int = 0


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}

    def register(self, manifest: PluginManifest) -> None:
        self._plugins[manifest.name] = manifest

    def list(self) -> list[PluginManifest]:
        return list(self._plugins.values())
