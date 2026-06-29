"""Public-contract versioning base (OC-RELEASE-001 §6/§7, OC-CONTRACTS-001).

Every public contract carries a ``schema_version`` of the form
``opencontext.<contract>.v<N>`` (REL-06, already MET across the contract families).
This module adds the rest of the book's versioning triad as an additive,
backward-compatible base:

* ``compatibility_version`` — the major contract line a reader must understand to
  consume the record. Defaults from ``schema_version`` (the ``vN`` suffix), so a
  contract that only ever set ``schema_version`` keeps a correct, derived value.
* ``deprecated_since`` — optional release string at which the contract was
  deprecated (``None`` while supported).
* ``stability`` — one of the five book stability levels (§6).

Adopting :class:`VersionedContract` is additive: the new fields default safely, so
existing serializations stay valid and legacy readers ignore the extra keys. The
enforcement test (``tests/core/test_contract_versioning.py``) asserts the triad
across the contracts that opt in, plus ``schema_version`` across the wider family.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, model_validator


#: Stability levels for public contracts and extension points (OC-RELEASE-001 §6).
class StabilityLevel(StrEnum):
    """The five stability levels every public contract declares (book §6)."""

    EXPERIMENTAL = "experimental"
    BETA = "beta"
    STABLE = "stable"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


_SCHEMA_RE = re.compile(r"\.v(\d+)$")


def compatibility_version_from_schema(schema_version: str) -> str:
    """Derive ``compatibility_version`` (e.g. ``"v2"``) from a ``schema_version``.

    ``opencontext.harness_report.v1`` → ``"v1"``. Falls back to ``"v1"`` when the
    schema string has no ``.vN`` suffix, so derivation never raises.
    """
    match = _SCHEMA_RE.search(schema_version or "")
    return f"v{match.group(1)}" if match else "v1"


class VersionedContract(BaseModel):
    """Mixin base carrying the full book versioning triad over ``schema_version``.

    Subclasses MUST define ``schema_version`` (kept as the existing literal). The
    ``compatibility_version`` defaults from it; ``stability`` defaults to ``beta``
    (pre-1.0 contracts) and ``deprecated_since`` is ``None`` until a deprecation
    is announced.
    """

    schema_version: str
    compatibility_version: str = ""
    deprecated_since: str | None = None
    stability: StabilityLevel = StabilityLevel.BETA

    @model_validator(mode="after")
    def _default_compatibility_version(self) -> VersionedContract:
        """Derive ``compatibility_version`` from ``schema_version`` when unset."""
        if not self.compatibility_version:
            object.__setattr__(
                self,
                "compatibility_version",
                compatibility_version_from_schema(self.schema_version),
            )
        return self


__all__ = [
    "StabilityLevel",
    "VersionedContract",
    "compatibility_version_from_schema",
]
