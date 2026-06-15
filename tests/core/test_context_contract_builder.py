"""Tests for ContextContractBuilder — 8 cases."""

from __future__ import annotations

from types import SimpleNamespace

from opencontext_core.context.planning.classifier import TaskClassifier
from opencontext_core.context.planning.contract import TIER_BUDGET, ContextContractBuilder


def make_builder() -> ContextContractBuilder:
    return ContextContractBuilder(classifier=TaskClassifier())


def test_security_query_critical_tier() -> None:
    builder = make_builder()
    contract = builder.build("fix security vulnerability in login")
    assert contract.risk_tier == "critical"
    gate_ids = [g.id for g in contract.must_verify]
    assert "security-scan" in gate_ids


def test_cheap_tier_token_budget() -> None:
    builder = make_builder()
    contract = builder.build("rename a variable in utils config")
    # configuration or feature low → cheap tier possible
    # just verify budget matches tier
    assert contract.token_budget == TIER_BUDGET[contract.risk_tier]


def test_critical_tier_token_budget() -> None:
    builder = make_builder()
    contract = builder.build("fix security vulnerability in production")
    assert contract.token_budget == 28_000


def test_is_complete_for_well_formed_contract() -> None:
    builder = make_builder()
    contract = builder.build("fix crash in auth middleware")
    # is_complete requires required_symbols or required_files AND must_verify
    assert contract.is_complete()


def test_manifest_language_propagates() -> None:
    manifest = SimpleNamespace(
        primary_language="python",
        detected_frameworks=[],
        file_count=100,
        project_name="myproject",
    )
    builder = make_builder()
    contract = builder.build("add feature", manifest=manifest)
    assert contract.language == "python"


def test_known_facts_include_project_name() -> None:
    manifest = SimpleNamespace(
        primary_language="python",
        detected_frameworks=[],
        file_count=50,
        project_name="my-service",
    )
    builder = make_builder()
    contract = builder.build("add feature", manifest=manifest)
    sources = [ref.source for ref in contract.known]
    assert any("my-service" in s for s in sources)


def test_mutation_gate_added_when_requires_mutation() -> None:
    builder = make_builder()
    contract = builder.build("fix security vulnerability in production auth")
    gate_ids = [g.id for g in contract.must_verify]
    assert "mutation-scan" in gate_ids


def test_empty_query_does_not_crash() -> None:
    builder = make_builder()
    contract = builder.build("")
    assert contract is not None
    assert contract.task == ""
