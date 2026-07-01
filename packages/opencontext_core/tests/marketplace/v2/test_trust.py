"""TrustLevel enum coverage."""

from __future__ import annotations

from opencontext_core.marketplace.v2.trust import TrustLevel


def test_trust_levels_present() -> None:
    assert {t.name for t in TrustLevel} == {
        "untrusted",
        "community",
        "verified",
        "official",
    }


def test_trust_ordering() -> None:
    # official > verified > community > untrusted
    assert TrustLevel.official > TrustLevel.verified
    assert TrustLevel.verified > TrustLevel.community
    assert TrustLevel.community > TrustLevel.untrusted
