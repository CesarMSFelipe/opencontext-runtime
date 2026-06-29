"""OpenContext Marketplace (PR-016).

Promotes the PR-015 plugin-distribution spine to the book's marketplace contract
(``31-marketplace-ecosystem-blueprint.md``): a first-class multi-asset package
format, a publish flow (leak gate + validators + versioning), publisher signing &
provenance, compatibility enforcement, trust levels, and package receipts.

Marketplace is optional and registry-agnostic — the runtime works without registry
access (the built-in fallback in ``plugin_system`` remains the consumption path).
The hosted public registry, ratings, and vendor publisher program are DEFERRED to
the post-1.0 ecosystem per the book.
"""

from __future__ import annotations

from opencontext_core.marketplace.install import (
    MarketplaceInstaller,
    MarketplaceInstallResult,
)
from opencontext_core.marketplace.manifest import (
    MARKETPLACE_SCHEMA_VERSION,
    MarketplacePackage,
    PackageCategory,
    PackageSignature,
    ProvidesBlock,
    Requires,
    is_marketplace_manifest,
)
from opencontext_core.marketplace.package import (
    build_package,
    load_manifest,
    package_manifest_hash,
    unpack_package,
)
from opencontext_core.marketplace.publish import PublishResult, publish_package
from opencontext_core.marketplace.receipt import (
    PackageReceipt,
    read_receipts,
    write_package_receipt,
)
from opencontext_core.marketplace.signing import PackageSigner, PackageVerifier
from opencontext_core.marketplace.trust import (
    TrustLevel,
    TrustPolicy,
    is_trust_allowed,
    requires_signature,
)
from opencontext_core.marketplace.versioning import is_compatible, is_valid_semver

__all__ = [
    "MARKETPLACE_SCHEMA_VERSION",
    "MarketplaceInstallResult",
    "MarketplaceInstaller",
    "MarketplacePackage",
    "PackageCategory",
    "PackageReceipt",
    "PackageSignature",
    "PackageSigner",
    "PackageVerifier",
    "ProvidesBlock",
    "PublishResult",
    "Requires",
    "TrustLevel",
    "TrustPolicy",
    "build_package",
    "is_compatible",
    "is_marketplace_manifest",
    "is_trust_allowed",
    "is_valid_semver",
    "load_manifest",
    "package_manifest_hash",
    "publish_package",
    "read_receipts",
    "requires_signature",
    "unpack_package",
    "write_package_receipt",
]
