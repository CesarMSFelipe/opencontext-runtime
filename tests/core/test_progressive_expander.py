"""Tests for ProgressiveExpander — 5 cases."""

from __future__ import annotations

from types import SimpleNamespace

from opencontext_core.context.planning.expansion import (
    EXPANSION_ORDER,
    ContextItem,
    ProgressiveExpander,
)


def make_plan(rounds: int = 2, radius: int = 1, include_memory: bool = False):
    return SimpleNamespace(
        expansion_rounds=rounds, graph_radius=radius, include_memory=include_memory
    )


def make_contract(required_symbols: list[str] | None = None):
    return SimpleNamespace(required_symbols=required_symbols or [])


def test_stops_at_max_rounds() -> None:
    expander = ProgressiveExpander()
    seeds = [ContextItem(id="a")]
    plan = make_plan(rounds=1)
    contract = make_contract()
    # round_num=2 exceeds expansion_rounds=1 → returns seeds unchanged
    result = expander.expand(seeds, plan, contract, round_num=2)
    assert result == seeds


def test_deduplicates() -> None:
    expander = ProgressiveExpander()
    seeds = [ContextItem(id="a"), ContextItem(id="a"), ContextItem(id="b")]
    plan = make_plan(rounds=2)
    contract = make_contract()
    result = expander.expand(seeds, plan, contract, round_num=1)
    ids = [item.id for item in result]
    assert ids.count("a") == 1


def test_expansion_order_constant() -> None:
    assert ProgressiveExpander.EXPANSION_ORDER == EXPANSION_ORDER
    assert EXPANSION_ORDER[0] == "summary"
    assert EXPANSION_ORDER[-1] == "dependencies"


def test_empty_seeds_returns_empty() -> None:
    expander = ProgressiveExpander()
    plan = make_plan()
    contract = make_contract()
    result = expander.expand([], plan, contract, round_num=1)
    assert result == []


def test_contract_satisfied_early_stops() -> None:
    expander = ProgressiveExpander()
    seeds = [ContextItem(id="auth_middleware"), ContextItem(id="token_validator")]
    plan = make_plan(rounds=3)
    # Contract requires symbols already covered by seeds
    contract = make_contract(required_symbols=["auth_middleware", "token_validator"])
    result = expander.expand(seeds, plan, contract, round_num=1)
    # Should return seeds without extra expansion
    ids = {item.id for item in result}
    assert "auth_middleware" in ids
    assert "token_validator" in ids
