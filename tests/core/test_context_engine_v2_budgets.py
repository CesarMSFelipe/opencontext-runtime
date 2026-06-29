"""PR-010 SPEC-CTX-010-10: per-workflow / per-node context budget tables."""

from __future__ import annotations

from opencontext_core.context.budget_table import (
    BUDGETS,
    OC_FLOW_NODES,
    SDD_NODES,
    assert_complete,
    known_nodes,
    resolve,
    workflow_total,
)


def test_every_known_node_resolves_a_budget() -> None:
    assert_complete()  # raises if any canonical node lacks an entry
    for workflow, node in known_nodes():
        assert resolve(workflow, node) >= 0


def test_oc_flow_per_node_splits_sum_within_4k_6k() -> None:
    total = workflow_total("oc_flow")
    assert 4000 <= total <= 6000
    # Every OC Flow node has an explicit split.
    for node in OC_FLOW_NODES:
        assert node in BUDGETS["oc_flow"]


def test_sdd_and_review_totals_match_book_table() -> None:
    assert 8000 <= resolve("sdd", "explore") <= 15000  # SDD Explore 8k-15k
    assert 6000 <= resolve("sdd", "design") <= 10000  # SDD Design 6k-10k
    assert 3000 <= resolve("review", "review") <= 5000  # Review 3k-5k
    for node in SDD_NODES:
        assert node in BUDGETS["sdd"]


def test_workflow_aliases_resolve() -> None:
    assert resolve("oc-flow", "gather_context") == resolve("oc_flow", "gather_context")
    assert resolve("sdd_explore", "explore") == resolve("sdd", "explore")


def test_unknown_node_is_still_resolvable() -> None:
    # Book invariant: every workflow node must have a resolvable budget.
    assert resolve("oc_flow", "nonexistent_node") > 0
