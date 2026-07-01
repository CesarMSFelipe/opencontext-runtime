"""REQ-mkt-v1-001: TrustLevel enforcement + official default."""

from __future__ import annotations

import pytest

from opencontext_core.marketplace.v2.package import (
    MarketplacePackage,
    install_package,
    TrustLevelRejected,
)
from opencontext_core.marketplace.v2.trust import TrustLevel


def test_REQ_mkt_v1_001_trust_level_enforced() -> None:
    pkg = MarketplacePackage(
        package_id="demo",
        name="Demo",
        version="1.0.0",
        publisher="acme",
        license="MIT",
        category="skill",
        trust=TrustLevel.community,
    )
    with pytest.raises(TrustLevelRejected):
        install_package(pkg, min_trust=TrustLevel.official)


def test_REQ_mkt_v1_001_official_default_passes() -> None:
    pkg = MarketplacePackage(
        package_id="official",
        name="Official",
        version="1.0.0",
        publisher="opencontext",
        license="Apache-2.0",
        category="skill",
        trust=TrustLevel.official,
    )
    receipt = install_package(pkg, min_trust=TrustLevel.official)
    assert receipt["installed"] is True