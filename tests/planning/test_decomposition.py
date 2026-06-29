"""Tests for ImplementationSlice + decompose (SPEC MP-004)."""

from __future__ import annotations

from opencontext_core.planning.decomposition import ImplementationSlice, decompose
from opencontext_core.planning.intent import parse_intent


def _intent() -> object:
    return parse_intent("Decompose the runtime backlog into slices.")


def test_decompose_yields_at_least_one_slice() -> None:
    slices = decompose(_intent(), ["MP-001", "MP-002"])
    assert len(slices) >= 1
    assert all(isinstance(s, ImplementationSlice) for s in slices)


def test_schema_version_is_slice_v1() -> None:
    slices = decompose(_intent(), ["MP-001"])
    assert slices[0].schema_version == "opencontext.slice.v1"


def test_every_requirement_in_exactly_one_slice() -> None:
    requirements = ["MP-001", "MP-002", "PR-003", "PR-004", "DOC-001"]
    slices = decompose(_intent(), requirements)

    seen: list[str] = []
    for s in slices:
        seen.extend(s.requirement_ids)

    # Each requirement appears exactly once, total preserved.
    assert sorted(seen) == sorted(requirements)
    assert len(seen) == len(set(seen))


def test_requirements_with_shared_prefix_group_together() -> None:
    slices = decompose(_intent(), ["MP-001", "MP-002", "PR-003"])
    by_key = {s.title: s.requirement_ids for s in slices}
    assert by_key["Implement MP"] == ["MP-001", "MP-002"]
    assert by_key["Implement PR"] == ["PR-003"]


def test_blank_requirements_are_dropped() -> None:
    slices = decompose(_intent(), ["MP-001", "   ", ""])
    covered = [r for s in slices for r in s.requirement_ids]
    assert covered == ["MP-001"]


def test_duplicate_requirements_collapse() -> None:
    slices = decompose(_intent(), ["MP-001", "MP-001"])
    covered = [r for s in slices for r in s.requirement_ids]
    assert covered == ["MP-001"]
