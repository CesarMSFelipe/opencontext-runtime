"""Package trust levels and policy gating (PR-016, book §31 Trust Levels).

The book defines six trust levels and states "Runtime policy may restrict
installation by trust level." This module is the one vocabulary: a ``TrustLevel``
enum plus a small ``TrustPolicy`` the installer consults before activation. The
default policy is permissive (it blocks nothing) so the runtime keeps working
without configuration; a deployment opts into restriction by blocking levels or
setting a minimum.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum


class TrustLevel(StrEnum):
    """The book's six package trust levels, highest to lowest."""

    OFFICIAL = "official"
    VERIFIED = "verified"
    COMMUNITY = "community"
    PRIVATE = "private"
    EXPERIMENTAL = "experimental"
    UNTRUSTED = "untrusted"


# Ordered rank used for the optional ``min_level`` floor. Higher = more trusted.
_RANK: dict[TrustLevel, int] = {
    TrustLevel.OFFICIAL: 5,
    TrustLevel.VERIFIED: 4,
    TrustLevel.COMMUNITY: 3,
    TrustLevel.PRIVATE: 2,
    TrustLevel.EXPERIMENTAL: 1,
    TrustLevel.UNTRUSTED: 0,
}

# Trust levels that the book requires a verified publisher signature for before
# activation (SPEC PR-016-PKG: "verify that signature on install for
# official/verified trust levels").
SIGNATURE_REQUIRED_LEVELS: frozenset[TrustLevel] = frozenset(
    {TrustLevel.OFFICIAL, TrustLevel.VERIFIED}
)


class TrustPolicy(BaseModel):
    """Runtime policy over package trust levels (book §31 Security).

    Permissive by default (blocks nothing, no floor) so an unconfigured runtime
    installs community/private packages unchanged. A deployment restricts by
    listing ``blocked_levels`` and/or setting a ``min_level`` floor.
    """

    model_config = ConfigDict(extra="forbid")

    blocked_levels: list[TrustLevel] = Field(
        default_factory=list,
        description="Trust levels installation is forbidden for.",
    )
    min_level: TrustLevel | None = Field(
        default=None,
        description="Minimum acceptable trust level (inclusive). None = no floor.",
    )


def requires_signature(level: TrustLevel) -> bool:
    """Whether a package at *level* must carry a verified publisher signature."""
    return level in SIGNATURE_REQUIRED_LEVELS


def is_trust_allowed(level: TrustLevel, policy: TrustPolicy | None = None) -> bool:
    """Return whether a package at *level* may be installed under *policy*.

    A ``None`` policy is the permissive default (everything allowed).
    """
    if policy is None:
        return True
    if level in policy.blocked_levels:
        return False
    if policy.min_level is not None and _RANK[level] < _RANK[policy.min_level]:
        return False
    return True
