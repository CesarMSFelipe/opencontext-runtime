"""Plugin manifest models with explicit, deny-by-default permissions.

PR-015 promotes the manifest to the book's Plugin Contract v1 (doc 12 §"Plugin
Manifest", doc 59 "Plugin Contract v1 — also public"): a typed ``schema_version``/
``id``/``requires``/``contributes`` envelope and the full deny-by-default
capability set (filesystem/network/command/provider/KG/memory). Every new field is
optional with a backward-compatible default so an existing on-disk ``plugin.json``
(no ``schema_version``/``contributes``) still validates.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.models.context import DataClassification

# Plugin Contract version (doc 59). Bumped on a breaking manifest change; the
# compatibility layer maps across versions. ``schema_version`` below carries the
# wire tag (``opencontext.plugin.v1``) used in YAML/JSON manifests.
PLUGIN_CONTRACT_VERSION = 1
PLUGIN_SCHEMA_VERSION = "opencontext.plugin.v1"


class PluginPermissions(BaseModel):
    """Explicit plugin permissions. All capabilities default to denied.

    Covers the six restricted operations the book §12 Security enumerates:
    filesystem (read/write), network, command (process execution), provider usage,
    KG writes, and memory writes. Each is an allowlist; an empty list means the
    capability is denied (deny-by-default).
    """

    model_config = ConfigDict(extra="forbid")

    read_paths: list[str] = Field(default_factory=list, description="Allowlisted read paths.")
    write_paths: list[str] = Field(default_factory=list, description="Allowlisted write paths.")
    network_hosts: list[str] = Field(
        default_factory=list,
        description="Allowlisted outbound hosts. Empty means no network access.",
    )
    mcp_servers: list[str] = Field(default_factory=list, description="Allowlisted MCP servers.")
    # PR-015: full capability set (book §12 Security). Deny-by-default.
    command: list[str] = Field(
        default_factory=list,
        description="Allowlisted process-execution commands. Empty = no command execution.",
    )
    provider: list[str] = Field(
        default_factory=list,
        description="Allowlisted provider routes. Empty = no provider usage.",
    )
    kg_write: list[str] = Field(
        default_factory=list,
        description="Allowlisted KG-write scopes. Empty = no KG writes.",
    )
    memory_write: list[str] = Field(
        default_factory=list,
        description="Allowlisted memory-write scopes. Empty = no memory writes.",
    )


class PluginRequires(BaseModel):
    """Compatibility requirements a plugin declares (book §12 Compatibility)."""

    model_config = ConfigDict(extra="forbid")

    runtime: str = Field(
        default=">=0.1",
        description="Minimum runtime version range, e.g. '>=2.0' (book manifest).",
    )
    api: str = Field(default="v1", description="Supported public API/contract version.")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Capability ids the plugin needs resolved before activation.",
    )
    plugins: list[str] = Field(
        default_factory=list,
        description="Other plugin ids this plugin depends on (resolved before activate).",
    )


class PluginContributions(BaseModel):
    """Typed ``contributes`` block over the extension points (book §12, PLG-CONV).

    Each field is a list of contribution ids the plugin provides for that point;
    ``extra="forbid"`` keeps the schema machine-checkable (an unknown point is a
    manifest error, not a silent no-op). 15 first-class points plus the two
    convergence additions (``execution_profiles``/``cache_providers``).
    """

    model_config = ConfigDict(extra="forbid")

    workflows: list[str] = Field(default_factory=list)
    personas: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    harnesses: list[str] = Field(default_factory=list)
    policies: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    kg_providers: list[str] = Field(default_factory=list)
    memory_providers: list[str] = Field(default_factory=list)
    context_strategies: list[str] = Field(default_factory=list)
    runtime_intelligence_analyzers: list[str] = Field(default_factory=list)
    studio_panels: list[str] = Field(default_factory=list)
    cli_commands: list[str] = Field(default_factory=list)
    mcp_tools: list[str] = Field(default_factory=list)
    project_templates: list[str] = Field(default_factory=list)
    benchmark_suites: list[str] = Field(default_factory=list)
    # PLG-CONV (OC-FINAL-CONVERGENCE-001 §6) additions.
    execution_profiles: list[str] = Field(default_factory=list)
    cache_providers: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """True when the plugin declares no typed contributions (legacy plugin)."""
        return not any(getattr(self, name) for name in type(self).model_fields)

    def items(self) -> list[tuple[str, list[str]]]:
        """Yield ``(extension_point, ids)`` pairs for every non-empty point."""
        return [
            (name, getattr(self, name)) for name in type(self).model_fields if getattr(self, name)
        ]


class PluginManifest(BaseModel):
    """Manifest for loading secure OpenContext plugins (Plugin Contract v1)."""

    model_config = ConfigDict(extra="forbid")

    # PR-015 typed envelope (book §12). All optional/defaulted for legacy validity.
    schema_version: str = Field(
        default=PLUGIN_SCHEMA_VERSION, description="Plugin manifest schema tag."
    )
    id: str | None = Field(
        default=None, description="Stable global plugin id, e.g. 'opencontext.demo'."
    )
    requires: PluginRequires = Field(
        default_factory=PluginRequires, description="Compatibility requirements."
    )
    contributes: PluginContributions = Field(
        default_factory=PluginContributions, description="Typed extension-point contributions."
    )

    name: str = Field(description="Stable plugin identifier.")
    version: str = Field(description="Plugin semantic version.")
    type: str = Field(default="analyzer", description="Plugin category.")
    description: str = Field(default="", description="Human-readable plugin description.")
    entrypoint: str = Field(description="Python entrypoint path for plugin activation.")
    max_data_classification: DataClassification = Field(
        default=DataClassification.INTERNAL,
        description="Maximum classification the plugin is allowed to process.",
    )
    permissions: PluginPermissions = Field(
        default_factory=PluginPermissions,
        description="Explicit permission grant set.",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict, description="Additional plugin metadata."
    )

    @classmethod
    def from_plugin_json(cls, data: dict[str, object]) -> PluginManifest:
        """Build a typed manifest from an on-disk ``plugin.json`` dict.

        The installer's on-disk shape (``entry_point``/``hooks``/``enabled``/
        ``author``/``installed_at``/…) is a superset of this typed contract, so a
        direct ``model_validate`` would trip ``extra="forbid"``. This adapter maps
        ``entry_point`` → ``entrypoint`` and keeps only the contract fields, so a
        legacy manifest validates with defaulted ``requires``/``contributes`` while
        unknown fields in *direct* construction are still rejected.
        """
        known = {
            "schema_version",
            "id",
            "requires",
            "contributes",
            "name",
            "version",
            "type",
            "description",
            "entrypoint",
            "max_data_classification",
            "permissions",
            "metadata",
        }
        payload: dict[str, object] = {k: v for k, v in data.items() if k in known}
        if "entrypoint" not in payload:
            payload["entrypoint"] = data.get("entry_point", "plugin.py")
        payload.setdefault("version", data.get("version", "0.1.0"))
        return cls.model_validate(payload)
