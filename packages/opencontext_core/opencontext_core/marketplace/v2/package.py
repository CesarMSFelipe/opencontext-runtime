"""PR-016 MarketplacePackage + install gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from opencontext_core.marketplace.v2.trust import TrustLevel

SCHEMA_VERSION = "opencontext.marketplace_package.v1"


class TrustLevelRejected(Exception):
    """Package trust level is below the required minimum."""


@dataclass
class MarketplacePackage:
    package_id: str
    name: str
    version: str
    publisher: str
    license: str
    category: str
    trust: TrustLevel = TrustLevel.community
    requires: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


def install_package(pkg: MarketplacePackage, *, min_trust: TrustLevel) -> dict[str, Any]:
    """Install gate: enforce trust level, return a receipt."""
    if pkg.trust < min_trust:
        raise TrustLevelRejected(
            f"package {pkg.package_id!r} trust={pkg.trust.name} < required min={min_trust.name}"
        )
    return {
        "installed": True,
        "package_id": pkg.package_id,
        "version": pkg.version,
        "trust": pkg.trust.name,
        "schema_version": pkg.schema_version,
    }
