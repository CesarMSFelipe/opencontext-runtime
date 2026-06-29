"""Contract guard for the Policy Engine (doc 59 §internal versioning / event family)."""

from __future__ import annotations

from opencontext_core.policy.models import (
    POLICY_CONTRACT_VERSION,
    POLICY_EVENT_FAMILY,
    PolicyDecision,
)
from opencontext_core.policy.presets import PolicyPreset
from opencontext_core.runtime.events import EventCategory


def test_policy_contract_version_pinned() -> None:
    # Bump deliberately on a breaking change; this guard catches accidental drift.
    assert POLICY_CONTRACT_VERSION == 1
    assert PolicyDecision(
        operation="x", decision="allow", reason="r", policy_id="p"
    ).contract_version == 1


def test_policy_event_family_is_a_known_category() -> None:
    assert POLICY_EVENT_FAMILY == "policy"
    assert POLICY_EVENT_FAMILY in {c.value for c in EventCategory}


def test_four_presets_exist() -> None:
    assert {p.value for p in PolicyPreset} == {
        "permissive",
        "balanced",
        "restricted",
        "air_gapped",
    }
