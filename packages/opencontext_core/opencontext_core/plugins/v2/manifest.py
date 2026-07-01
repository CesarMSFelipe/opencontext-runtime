"""PR-015 PluginManifest — Pydantic-free, dict-round-trip v1 schema."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PLUGIN_SCHEMA_VERSION = "opencontext.plugin.v1"


class ManifestSchemaError(Exception):
    """Manifest shape does not match the expected schema_version."""


@dataclass
class PluginManifest:
    """Plugin envelope: identity + requires/provides capability lists."""

    plugin_id: str
    version: str
    requires: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    schema_version: str = PLUGIN_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        if data.get("schema_version") != PLUGIN_SCHEMA_VERSION:
            raise ManifestSchemaError(
                f"schema_version mismatch: expected {PLUGIN_SCHEMA_VERSION}, "
                f"got {data.get('schema_version')!r}"
            )
        if "plugin_id" not in data or "version" not in data:
            raise ManifestSchemaError("missing plugin_id or version")
        return cls(
            plugin_id=data["plugin_id"],
            version=data["version"],
            requires=list(data.get("requires", [])),
            provides=list(data.get("provides", [])),
            permissions=list(data.get("permissions", [])),
            schema_version=data.get("schema_version", PLUGIN_SCHEMA_VERSION),
        )