"""PR-016 TrustLevel — ranked enum for marketplace packages."""

from __future__ import annotations

from enum import IntEnum


class TrustLevel(IntEnum):
    untrusted = 0
    community = 1
    verified = 2
    official = 3
