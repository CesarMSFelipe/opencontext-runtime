"""Tests for skills.v2.bundles — load named bundles (A6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.skills.v2.bundles import load_bundle


BUNDLES_ROOT = Path(__file__).parents[3] / "opencontext_core" / "skills" / "bundles_yaml"


def test_bundles_sdd_yaml_loads() -> None:
    """bundles_yaml/sdd.yaml resolves to a SkillBundle."""
    if not (BUNDLES_ROOT / "sdd.yaml").exists():
        pytest.skip("sdd bundle not present")
    bundle = load_bundle("sdd", root=BUNDLES_ROOT)
    assert bundle.id == "sdd"


def test_bundles_oc_flow_yaml_loads() -> None:
    """bundles_yaml/oc-flow.yaml resolves to a SkillBundle."""
    if not (BUNDLES_ROOT / "oc-flow.yaml").exists():
        pytest.skip("oc-flow bundle not present")
    bundle = load_bundle("oc-flow", root=BUNDLES_ROOT)
    assert bundle.id == "oc-flow"
