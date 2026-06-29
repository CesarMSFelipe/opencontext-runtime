"""Marketplace package manifest (PR-016, book §31 Package Manifest).

A ``MarketplacePackage`` is the first-class, multi-asset bundle the book defines as
``opencontext.marketplace_package.v1``. It is a *superset* of the single-asset
``PluginManifest``: it carries ``id``/``publisher``/``category``/``license``, a
``requires.opencontext`` version range, a ``provides`` block bundling
skills/personas/harnesses/workflows/benchmarks, a reused ``PluginPermissions``
block, a trust level, and an optional publisher ``signature``.

Back-compat: a legacy on-disk ``plugin.json`` (no ``schema_version`` /
``opencontext.plugin.v1``) is *not* a marketplace package — :func:`is_marketplace_manifest`
returns False for it and the legacy single-asset install path stays unchanged.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC, StrEnum
from opencontext_core.marketplace.trust import TrustLevel
from opencontext_core.plugins.manifest import PluginPermissions

MARKETPLACE_SCHEMA_VERSION = "opencontext.marketplace_package.v1"

# Default manifest filename inside a package bundle.
PACKAGE_MANIFEST_NAME = "marketplace.json"


class PackageCategory(StrEnum):
    """Package categories from the book's marketplace blueprint (§31)."""

    CORE = "core-pack"
    FRAMEWORK = "framework-pack"
    ENTERPRISE = "enterprise-pack"
    SECURITY = "security-pack"
    PROVIDER = "provider-pack"
    BENCHMARK = "benchmark-pack"
    COMMUNITY = "community-pack"


class Requires(BaseModel):
    """Compatibility requirements a marketplace package declares."""

    model_config = ConfigDict(extra="forbid")

    opencontext: str = Field(
        default=">=0.1",
        description="OpenContext version range, e.g. '>=1.0,<2.0' (book manifest).",
    )


class ProvidesBlock(BaseModel):
    """Multi-asset bundle: the assets a package contributes (book §31)."""

    model_config = ConfigDict(extra="forbid")

    skills: list[str] = Field(default_factory=list)
    personas: list[str] = Field(default_factory=list)
    harnesses: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    benchmarks: list[str] = Field(default_factory=list)
    policies: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """True when the package declares no contributed assets."""
        return not any(getattr(self, name) for name in type(self).model_fields)

    def items(self) -> list[tuple[str, list[str]]]:
        """Yield ``(asset_kind, ids)`` pairs for every non-empty asset list."""
        return [
            (name, getattr(self, name))
            for name in type(self).model_fields
            if getattr(self, name)
        ]


class PackageSignature(BaseModel):
    """Publisher signature over a package's manifest hash (PR-016).

    HMAC-sha256 over :func:`marketplace.package.package_manifest_hash` today; the
    ``public_key_hint`` seam carries asymmetric publisher keys for the
    ``official``/``verified`` path without a crypto dependency now (mirrors the
    ``workflow_packs.signing`` precedent).
    """

    model_config = ConfigDict(extra="forbid")

    algorithm: str = Field(default="hmac-sha256", description="Signature algorithm.")
    manifest_hash: str = Field(description="Hash of the package file manifest.")
    signature: str = Field(description="Signature over the manifest hash.")
    publisher: str = Field(default="", description="Signing publisher id.")
    signed_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    public_key_hint: str | None = Field(
        default=None,
        description="Asymmetric public-key hint; absent ⇒ local HMAC integrity.",
    )


class MarketplacePackage(BaseModel):
    """A first-class marketplace package manifest (``opencontext.marketplace_package.v1``)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default=MARKETPLACE_SCHEMA_VERSION, description="Marketplace package schema tag."
    )
    id: str = Field(description="Stable global package id, e.g. 'vendor.package'.")
    name: str = Field(description="Human-readable package name.")
    version: str = Field(description="Package semantic version (X.Y.Z).")
    publisher: str = Field(default="", description="Publishing vendor/author id.")
    license: str = Field(default="", description="SPDX license id.")
    category: PackageCategory = Field(
        default=PackageCategory.FRAMEWORK, description="Package category."
    )
    description: str = Field(default="", description="Human-readable description.")

    requires: Requires = Field(
        default_factory=Requires, description="Compatibility requirements."
    )
    provides: ProvidesBlock = Field(
        default_factory=ProvidesBlock, description="Multi-asset contribution bundle."
    )
    permissions: PluginPermissions = Field(
        default_factory=PluginPermissions, description="Deny-by-default permissions."
    )
    trust_level: TrustLevel = Field(
        default=TrustLevel.COMMUNITY, description="Package trust level."
    )
    signature: PackageSignature | None = Field(
        default=None, description="Publisher signature (set on publish)."
    )
    metadata: dict[str, str] = Field(default_factory=dict, description="Extra metadata.")

    def granted_permissions(self) -> list[str]:
        """Flatten the declared permission allowlists into ``capability:value`` strings.

        Used by the install receipt to record the approved permission set.
        """
        granted: list[str] = []
        perms = self.permissions
        for cap in (
            "read_paths",
            "write_paths",
            "network_hosts",
            "mcp_servers",
            "command",
            "provider",
            "kg_write",
            "memory_write",
        ):
            for value in getattr(perms, cap, []):
                granted.append(f"{cap}:{value}")
        return granted


def is_marketplace_manifest(data: dict[str, object]) -> bool:
    """True when a parsed manifest dict is a marketplace package (not a legacy plugin)."""
    return data.get("schema_version") == MARKETPLACE_SCHEMA_VERSION
