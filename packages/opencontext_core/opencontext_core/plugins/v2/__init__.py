"""PR-015 Plugin SDK v1 public surface."""

from __future__ import annotations

from opencontext_core.plugins.v2.conformance import (
    ConformanceReport,
    ConformanceSuite,
)
from opencontext_core.plugins.v2.lifecycle import (
    IllegalTransitionError,
    PluginState,
    PluginStateMachine,
)
from opencontext_core.plugins.v2.manifest import (
    PLUGIN_SCHEMA_VERSION,
    ManifestSchemaError,
    PluginManifest,
)

__all__ = [
    "PLUGIN_SCHEMA_VERSION",
    "ConformanceReport",
    "ConformanceSuite",
    "IllegalTransitionError",
    "ManifestSchemaError",
    "PluginManifest",
    "PluginState",
    "PluginStateMachine",
]