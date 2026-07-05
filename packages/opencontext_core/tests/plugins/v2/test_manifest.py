"""REQ-plugin-v1-001: PluginManifest round-trip + schema mismatch."""

from __future__ import annotations

import pytest

from opencontext_core.plugins.v2.manifest import (
    PLUGIN_SCHEMA_VERSION,
    ManifestSchemaError,
    PluginManifest,
)


def test_REQ_plugin_v1_001_round_trip() -> None:
    m = PluginManifest(plugin_id="demo", version="1.0.0", requires=[], provides=[])
    d = m.to_dict()
    again = PluginManifest.from_dict(d)
    assert again.plugin_id == "demo"
    assert again.version == "1.0.0"


def test_REQ_plugin_v1_001_schema_mismatch() -> None:
    with pytest.raises(ManifestSchemaError):
        PluginManifest.from_dict(
            {"schema_version": "opencontext.plugin.v0", "plugin_id": "x", "version": "0.0.1"}
        )


def test_schema_version_constant() -> None:
    assert PLUGIN_SCHEMA_VERSION == "opencontext.plugin.v1"
