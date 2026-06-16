"""Tests for ContextPlan model."""

from opencontext_core.models.context_contract import VerificationGate
from opencontext_core.models.context_plan import ContextPlan


def test_context_plan_fields():
    plan = ContextPlan(
        mode="verified",
        tier="critical",
        budget_tokens=28000,
        must_read=["auth.py"],
        should_read=["utils.py"],
        must_verify=[VerificationGate(id="run-tests")],
        include_tests=True,
        include_memory=True,
        include_semantic=False,
        compression_strategy="none",
        graph_radius=2,
        expansion_rounds=3,
        memory_query="login crash",
    )
    assert plan.tier == "critical"
    assert plan.budget_tokens == 28000
    assert plan.expansion_rounds == 3


def test_compression_strategy_values():
    for strategy in ("none", "terse", "compact", "deep"):
        plan = ContextPlan(
            mode="fast",
            tier="cheap",
            budget_tokens=8000,
            must_read=[],
            should_read=[],
            must_verify=[],
            include_tests=False,
            include_memory=False,
            include_semantic=False,
            compression_strategy=strategy,
            graph_radius=1,
            expansion_rounds=1,
            memory_query="",
        )
        assert plan.compression_strategy == strategy


def test_tier_budget_correlation():
    cheap = ContextPlan(
        mode="fast",
        tier="cheap",
        budget_tokens=8000,
        must_read=[],
        should_read=[],
        must_verify=[],
        include_tests=False,
        include_memory=False,
        include_semantic=False,
        compression_strategy="terse",
        graph_radius=1,
        expansion_rounds=1,
        memory_query="",
    )
    critical = ContextPlan(
        mode="verified",
        tier="critical",
        budget_tokens=28000,
        must_read=[],
        should_read=[],
        must_verify=[],
        include_tests=True,
        include_memory=True,
        include_semantic=False,
        compression_strategy="none",
        graph_radius=2,
        expansion_rounds=3,
        memory_query="",
    )
    assert cheap.budget_tokens < critical.budget_tokens
