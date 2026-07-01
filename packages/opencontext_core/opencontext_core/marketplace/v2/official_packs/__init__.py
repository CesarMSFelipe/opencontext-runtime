"""PR-016 3 official framework packs (REQ-mkt-v1-004)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from opencontext_core.marketplace.v2.package import MarketplacePackage
from opencontext_core.marketplace.v2.trust import TrustLevel

OFFICIAL_PACK_IDS: tuple[str, ...] = (
    "python-pytest",
    "typescript-eslint",
    "php-phpunit",
)


_PACKS: dict[str, MarketplacePackage] = {
    "python-pytest": MarketplacePackage(
        package_id="python-pytest",
        name="Python + pytest",
        version="1.0.0",
        publisher="opencontext",
        license="Apache-2.0",
        category="toolchain",
        trust=TrustLevel.official,
        provides=["pytest", "ruff", "mypy"],
    ),
    "typescript-eslint": MarketplacePackage(
        package_id="typescript-eslint",
        name="TypeScript + ESLint",
        version="1.0.0",
        publisher="opencontext",
        license="Apache-2.0",
        category="toolchain",
        trust=TrustLevel.official,
        provides=["typescript", "eslint"],
    ),
    "php-phpunit": MarketplacePackage(
        package_id="php-phpunit",
        name="PHP + PHPUnit",
        version="1.0.0",
        publisher="opencontext",
        license="Apache-2.0",
        category="toolchain",
        trust=TrustLevel.official,
        provides=["php", "phpunit"],
    ),
}


def get_pack(package_id: str) -> dict[str, Any] | None:
    pkg = _PACKS.get(package_id)
    if pkg is None:
        return None
    return {
        "package_id": pkg.package_id,
        "name": pkg.name,
        "version": pkg.version,
        "publisher": pkg.publisher,
        "trust": pkg.trust.name,
        "license": pkg.license,
        "category": pkg.category,
    }


def all_packs() -> Iterator[MarketplacePackage]:
    return iter(_PACKS.values())
