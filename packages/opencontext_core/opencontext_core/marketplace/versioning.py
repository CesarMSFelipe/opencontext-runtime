"""Semantic-version validation and compatibility-range checks (PR-016).

Reuses the dependency-free clause evaluator from ``plugins.compatibility`` (KEY
DISCOVERY 2/4 — the comparison logic already exists) and adds comma-separated
range support (``">=1.0,<2.0"``) plus a strict ``X.Y.Z`` semver gate for publish.
"""

from __future__ import annotations

import re

from opencontext_core.plugins.compatibility import _satisfies

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def is_valid_semver(version: str) -> bool:
    """Strict ``MAJOR.MINOR.PATCH`` (optional pre-release/build) check."""
    return bool(_SEMVER_RE.match(version.strip()))


def is_compatible(requires_spec: str, core_version: str) -> tuple[bool, str]:
    """Check a comma-separated version range against the running core version.

    Returns ``(ok, reason)``. An empty/absent requirement never blocks
    (compatibility is not falsely failed). Every comma clause must hold.
    """
    spec = (requires_spec or "").strip()
    if not spec:
        return True, "no requirement declared"
    for clause in spec.split(","):
        clause = clause.strip()
        if clause and not _satisfies(core_version, clause):
            return False, f"requires opencontext {spec}, core is {core_version}"
    return True, "compatible"
