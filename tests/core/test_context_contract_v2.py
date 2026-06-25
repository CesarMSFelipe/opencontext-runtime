"""Tests for ContextContract v2 fields + ContractCoverage (Phase 3 / Workstream D)."""

from __future__ import annotations

import yaml

from opencontext_core.context.planning.classifier import TaskClassifier
from opencontext_core.context.planning.contract import TIER_PROFILE, ContextContractBuilder
from opencontext_core.models.context_contract import (
    ContextContract,
    ContractCoverage,
    VerificationGate,
)


def _make_contract(**overrides) -> ContextContract:
    defaults = dict(
        task="fix login crash",
        task_type="bugfix",
        risk_level="high",
        risk_tier="critical",
        required_symbols=["auth.validate_token"],
        required_files=["auth.py"],
        must_verify=[VerificationGate(id="run-tests")],
        token_budget=28000,
    )
    defaults.update(overrides)
    return ContextContract(**defaults)


# ── schema_version + contract_id ──────────────────────────────────────────────


def test_schema_version_is_v2() -> None:
    c = _make_contract()
    assert c.schema_version == "opencontext.context_contract.v2"


def test_contract_id_auto_filled() -> None:
    c = _make_contract()
    assert c.contract_id is not None
    assert c.contract_id.startswith("cc-")


def test_contract_id_deterministic_for_same_identity() -> None:
    a = _make_contract()
    b = _make_contract()
    assert a.contract_id == b.contract_id


def test_contract_id_differs_by_task() -> None:
    a = _make_contract(task="fix login crash")
    b = _make_contract(task="add a new endpoint")
    assert a.contract_id != b.contract_id


def test_contract_id_respected_when_supplied() -> None:
    c = _make_contract(contract_id="cc-custom")
    assert c.contract_id == "cc-custom"


# ── optional v2 profile fields ────────────────────────────────────────────────


def test_v2_profile_fields_default_none() -> None:
    c = _make_contract()
    assert c.workflow_hint is None
    assert c.policy_profile is None
    assert c.quality_profile is None
    assert c.coverage is None


def test_v2_fields_round_trip_via_yaml() -> None:
    c = _make_contract(workflow_hint="sdd", policy_profile="strict", quality_profile="strict")
    parsed = yaml.safe_load(c.to_yaml())
    assert parsed["workflow_hint"] == "sdd"
    assert parsed["policy_profile"] == "strict"
    assert parsed["schema_version"] == "opencontext.context_contract.v2"
    assert parsed["contract_id"].startswith("cc-")


# ── ContractCoverage ──────────────────────────────────────────────────────────


def test_coverage_ratio_empty_is_complete() -> None:
    cov = ContractCoverage()
    assert cov.ratio() == 1.0
    assert cov.is_complete() is True


def test_coverage_ratio_partial() -> None:
    cov = ContractCoverage(required_symbols=4, resolved_symbols=1)
    assert cov.ratio() == 0.25
    assert cov.is_complete() is False


def test_coverage_ratio_capped_at_one() -> None:
    cov = ContractCoverage(required_symbols=2, resolved_symbols=5)
    assert cov.ratio() == 1.0


def test_coverage_complete_when_all_resolved() -> None:
    cov = ContractCoverage(
        required_symbols=2,
        resolved_symbols=2,
        required_files=1,
        resolved_files=1,
    )
    assert cov.is_complete() is True
    assert cov.ratio() == 1.0


def test_coverage_forbids_extra_fields() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ContractCoverage(required_symbols=1, bogus=2)


# ── builder populates v2 ──────────────────────────────────────────────────────


def _builder() -> ContextContractBuilder:
    return ContextContractBuilder(classifier=TaskClassifier())


def test_builder_sets_workflow_hint_default() -> None:
    c = _builder().build("fix crash in auth middleware")
    assert c.workflow_hint == "sdd"


def test_builder_honors_workflow_hint_override() -> None:
    c = _builder().build("rename a variable", workflow_hint="quickfix")
    assert c.workflow_hint == "quickfix"


def test_builder_sets_tier_profiles() -> None:
    c = _builder().build("fix security vulnerability in production auth")
    assert c.risk_tier == "critical"
    assert c.policy_profile == TIER_PROFILE["critical"]
    assert c.quality_profile == TIER_PROFILE["critical"]


def test_builder_attaches_failclosed_coverage() -> None:
    c = _builder().build("fix crash in auth middleware")
    assert c.coverage is not None
    # Nothing resolved at build time → fail-closed (incomplete unless 0 required).
    assert c.coverage.resolved_symbols == 0
    if c.coverage.required_symbols > 0:
        assert c.coverage.is_complete() is False


def test_builder_contract_id_present() -> None:
    c = _builder().build("add a feature")
    assert c.contract_id is not None and c.contract_id.startswith("cc-")
