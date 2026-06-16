"""Tests for ContextPlanner — 6 cases."""

from __future__ import annotations

from opencontext_core.context.planning.classifier import TaskClassifier
from opencontext_core.context.planning.contract import ContextContractBuilder
from opencontext_core.context.planning.planner import TIER_BUDGET, TIER_RADIUS, ContextPlanner


def make_contract(query: str):
    builder = ContextContractBuilder(classifier=TaskClassifier())
    return builder.build(query)


def test_cheap_tier_uses_terse() -> None:
    contract = make_contract("rename config setting in utils")
    contract = contract.model_copy(update={"risk_tier": "cheap"})
    planner = ContextPlanner()
    plan = planner.plan(contract)
    assert plan.compression_strategy == "terse"


def test_precise_tier_uses_compact() -> None:
    contract = make_contract("add new feature endpoint")
    contract = contract.model_copy(update={"risk_tier": "precise"})
    planner = ContextPlanner()
    plan = planner.plan(contract)
    assert plan.compression_strategy == "compact"


def test_critical_tier_uses_none_and_verified_mode() -> None:
    contract = make_contract("fix security vulnerability in production")
    planner = ContextPlanner()
    plan = planner.plan(contract)
    assert plan.compression_strategy == "none"
    assert plan.mode == "verified"


def test_budget_scales_with_tier() -> None:
    for tier, expected_budget in TIER_BUDGET.items():
        contract = make_contract("fix bug")
        contract = contract.model_copy(update={"risk_tier": tier})
        planner = ContextPlanner()
        plan = planner.plan(contract)
        assert plan.budget_tokens == expected_budget


def test_graph_radius_scales_with_tier() -> None:
    for tier, expected_radius in TIER_RADIUS.items():
        contract = make_contract("fix bug")
        contract = contract.model_copy(update={"risk_tier": tier})
        planner = ContextPlanner()
        plan = planner.plan(contract)
        assert plan.graph_radius == expected_radius


def test_include_semantic_false_when_not_available() -> None:
    contract = make_contract("add feature")
    planner = ContextPlanner(semantic_available=False)
    plan = planner.plan(contract)
    assert plan.include_semantic is False
