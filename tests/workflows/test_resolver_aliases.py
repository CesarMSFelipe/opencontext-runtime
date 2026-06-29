"""WR2 / RES1 / BAK1 — alias table, resolver, and legacy parity tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.workflows import (
    WorkflowRegistry,
    WorkflowResolutionError,
    WorkflowResolver,
    resolve_alias,
)
from opencontext_core.workflows.aliases import UnknownWorkflowAlias


def _resolver() -> WorkflowResolver:
    return WorkflowResolver(WorkflowRegistry.with_builtins())


def test_resolve_alias_quick() -> None:
    """WR2: quick maps to sdd + the quick profile."""
    assert resolve_alias("quick") == ("sdd", "quick")


def test_resolve_alias_all_legacy_names() -> None:
    """WR2: full/standard/quick/sdd all resolve to the sdd workflow id."""
    assert resolve_alias("full") == ("sdd", "full")
    assert resolve_alias("standard") == ("sdd", "standard")
    assert resolve_alias("sdd") == ("sdd", "full")


def test_resolve_alias_unknown_raises() -> None:
    """WR2: an unknown alias raises a typed error."""
    with pytest.raises(UnknownWorkflowAlias):
        resolve_alias("not-a-workflow")


def test_resolve_standard_returns_definition_and_profile() -> None:
    """RES1: resolve('standard') returns the SDD definition and 'standard' profile."""
    resolved = _resolver().resolve("standard")
    assert resolved.definition.id == "sdd"
    assert resolved.profile == "standard"
    assert resolved.alias_used == "standard"


def test_resolve_unknown_name_raises() -> None:
    """RES1: an unknown workflow name is rejected."""
    with pytest.raises(WorkflowResolutionError):
        _resolver().resolve("totally-unknown")


@pytest.mark.parametrize("name", ["full", "standard", "quick", "sdd"])
def test_registry_resolution_parity_with_legacy(name: str, tmp_path: Path) -> None:
    """BAK1: registry-resolved phase order equals legacy schedule_phases today."""
    legacy = HarnessRunner(root=tmp_path).schedule_phases(name)
    resolved = _resolver().resolve(name)
    assert resolved.phase_order == legacy


def test_full_resolves_to_nine_phase_order(tmp_path: Path) -> None:
    """BAK1: full resolves to the nine-phase SDD order."""
    resolved = _resolver().resolve("full")
    assert resolved.phase_order == [
        "explore",
        "propose",
        "spec",
        "design",
        "tasks",
        "apply",
        "verify",
        "review",
        "archive",
    ]


def test_quick_resolves_to_reduced_track() -> None:
    """BAK1: quick resolves to the reduced explore/apply/verify track."""
    assert _resolver().resolve("quick").phase_order == ["explore", "apply", "verify"]


def test_resolve_alias_legacy_subset_and_quality_tracks() -> None:
    """WR2/VDM-004: the explore-only/apply-only subsets and the quality tracks alias."""
    assert resolve_alias("explore-only") == ("sdd", "explore-only")
    assert resolve_alias("apply-only") == ("sdd", "apply-only")
    assert resolve_alias("full+judgment") == ("sdd-quality", "full+judgment")
    assert resolve_alias("full+gga") == ("sdd-quality", "full+gga")
    assert resolve_alias("full+quality") == ("sdd-quality", "full+quality")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("explore-only", ["explore"]),
        ("apply-only", ["apply", "verify", "archive"]),
        (
            "full+judgment",
            [
                "explore",
                "propose",
                "spec",
                "design",
                "tasks",
                "apply",
                "verify",
                "review",
                "archive",
                "judgment",
            ],
        ),
        (
            "full+gga",
            [
                "explore",
                "propose",
                "spec",
                "design",
                "tasks",
                "apply",
                "verify",
                "review",
                "archive",
                "gga",
            ],
        ),
        (
            "full+quality",
            [
                "explore",
                "propose",
                "spec",
                "design",
                "tasks",
                "apply",
                "verify",
                "review",
                "archive",
                "gga",
                "judgment",
            ],
        ),
    ],
)
def test_legacy_tracks_resolve_to_expected_phase_order(name: str, expected: list[str]) -> None:
    """BAK1/VDM-004: every known legacy track resolves to its legacy phase order."""
    resolved = _resolver().resolve(name)
    assert resolved.phase_order == expected
    assert resolved.alias_used == name


def test_quality_tracks_back_onto_sdd_quality_definition() -> None:
    """VDM-004: the +judgment/+gga/+quality tracks resolve onto sdd-quality."""
    for name in ("full+judgment", "full+gga", "full+quality"):
        assert _resolver().resolve(name).definition.id == "sdd-quality"
