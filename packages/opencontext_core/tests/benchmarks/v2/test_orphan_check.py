"""Orphan check — release cannot ship with orphaned or proposed-status capabilities.

The capability registry is the single source of truth for which v2
modules ship in a release. A capability id that is referenced by
SPEC, the architecture coverage report, or any testsuite but is *not*
declared in the registry is an orphan; a capability marked
``proposed`` is not yet ready. Both block the release verdict.
"""

from __future__ import annotations

import pytest

from opencontext_core.benchmarks.v2.orphan_check import (
    ORPHAN_STATUSES,
    RELEASE_STATUSES,
    check_orphans,
    check_proposed_status,
)


def test_orphan_blocks_release() -> None:
    """An unknown capability id is an orphan and blocks the release."""
    declared: set[str] = {"graph.v2", "context.v2"}
    referenced: set[str] = {"graph.v2", "context.v2", "ghost.v2"}

    orphans = check_orphans(declared=declared, referenced=referenced)
    assert len(orphans) == 1
    assert orphans[0].capability_id == "ghost.v2"
    assert orphans[0].reason == "orphan"
    assert orphans[0].blocks_release is True


def test_proposed_status_rejected() -> None:
    """A capability marked ``proposed`` is not ready for release."""
    statuses = {"graph.v2": "stable", "context.v2": "proposed"}
    rejected = check_proposed_status(statuses)
    assert rejected == ["context.v2"]


def test_release_statuses_are_a_closed_set() -> None:
    """Only the documented release statuses pass the gate."""
    # Anything not in RELEASE_STATUSES is, by construction, not
    # shippable — including the common failure modes ("proposed",
    # "draft", "deprecated", "experimental", "").
    assert "proposed" in ORPHAN_STATUSES
    assert "draft" in ORPHAN_STATUSES
    assert "stable" in RELEASE_STATUSES
    assert "deprecated" in RELEASE_STATUSES  # deprecation is a release-managed state


def test_no_orphans_when_sets_match() -> None:
    """Healthy tree: declared == referenced produces no orphans."""
    declared = {"graph.v2", "context.v2"}
    referenced = {"graph.v2", "context.v2"}
    assert check_orphans(declared=declared, referenced=referenced) == []


def test_no_proposed_when_all_stable() -> None:
    """Healthy tree: all-stable statuses produce no rejections."""
    assert check_proposed_status({"graph.v2": "stable"}) == []


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
