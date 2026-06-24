"""Tests for PolicySimulator."""

from __future__ import annotations

from opencontext_core.tools.policy import ToolPermissionPolicy
from opencontext_core.tools.simulator import PolicySimulator, SimulatedDecision


def _make_policy(*allowed: str) -> ToolPermissionPolicy:
    return ToolPermissionPolicy(allowed_tools=set(allowed))


def test_all_allowed():
    policy = _make_policy("opencontext_search", "opencontext_context")
    sim = PolicySimulator(policy)
    results = sim.simulate(["opencontext_search", "opencontext_context"])
    assert all(r.decision == "allowed" for r in results)


def test_all_denied():
    policy = _make_policy("opencontext_search")
    sim = PolicySimulator(policy)
    results = sim.simulate(["opencontext_replace_symbol_body", "opencontext_run"])
    assert all(r.decision == "denied" for r in results)


def test_mixed():
    policy = _make_policy("opencontext_search")
    sim = PolicySimulator(policy)
    results = sim.simulate(["opencontext_search", "opencontext_run"])
    assert results[0].decision == "allowed"
    assert results[1].decision == "denied"


def test_explicit_deny_reason():
    policy = ToolPermissionPolicy(
        allowed_tools={"opencontext_search"},
        denied_tools={"opencontext_run"},
    )
    sim = PolicySimulator(policy)
    results = sim.simulate(["opencontext_run"])
    assert results[0].reason == "explicit_deny"


def test_not_allowlisted_reason():
    policy = _make_policy("opencontext_search")
    sim = PolicySimulator(policy)
    results = sim.simulate(["opencontext_context"])
    assert results[0].reason == "not_allowlisted"


def test_empty_list():
    policy = _make_policy("opencontext_search")
    sim = PolicySimulator(policy)
    assert sim.simulate([]) == []


def test_returns_simulated_decision_objects():
    policy = _make_policy("opencontext_search")
    sim = PolicySimulator(policy)
    results = sim.simulate(["opencontext_search"])
    assert isinstance(results[0], SimulatedDecision)
    assert results[0].tool == "opencontext_search"


def test_order_preserved():
    policy = _make_policy("opencontext_search")
    tools = ["opencontext_run", "opencontext_search", "opencontext_context"]
    sim = PolicySimulator(policy)
    results = sim.simulate(tools)
    assert [r.tool for r in results] == tools
