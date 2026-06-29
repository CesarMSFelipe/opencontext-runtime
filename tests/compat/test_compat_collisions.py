"""Name-collision resolution policy (SPEC CL-009)."""

from __future__ import annotations

from opencontext_core.compat import COLLISION_REGISTRY, CollisionRule, collision


def test_all_four_collisions_covered() -> None:
    names = {c.name for c in COLLISION_REGISTRY}
    assert names == {"ProviderGateway", "CostReport", "EvolutionProposal", "EvidenceRef"}


def test_no_duplicate_or_unresolved() -> None:
    names = [c.name for c in COLLISION_REGISTRY]
    assert len(names) == len(set(names))
    for entry in COLLISION_REGISTRY:
        assert isinstance(entry.rule, CollisionRule)
        assert entry.vnext_owner_pr
        assert entry.legacy_path
        assert entry.note


def test_specific_rules() -> None:
    provider = collision("ProviderGateway")
    assert provider is not None
    assert provider.rule is CollisionRule.namespace
    assert provider.vnext_owner_pr == "PR-012"

    # PR-011 (design DEC-2): the legacy aggregate-ledger CostReport is KEPT as-is
    # and the book estimate-vs-actual CostReport lives in models/intelligence.py —
    # the two coexist, disambiguated by package (namespace), not superseded.
    assert collision("CostReport").rule is CollisionRule.namespace
    assert collision("CostReport").vnext_owner_pr == "PR-011"

    assert collision("EvolutionProposal").rule is CollisionRule.alias
    assert collision("EvolutionProposal").vnext_owner_pr == "PR-011"

    assert collision("EvidenceRef").rule is CollisionRule.supersede
    assert collision("EvidenceRef").vnext_owner_pr == "PR-008"


def test_unknown_collision_returns_none() -> None:
    assert collision("NotAThing") is None
