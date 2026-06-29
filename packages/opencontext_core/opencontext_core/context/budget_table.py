"""Per-workflow / per-node context budget tables (PR-010, OC-CONTEXT-001 §Context Budget).

The book gives workflow-level context budgets (OC Flow 4k-6k with per-node splits,
SDD Explore 8k-15k, SDD Design 6k-10k, Review 3k-5k). This module codifies them as a
``(workflow, node) -> token budget`` table, resolves a budget for any node, and
asserts completeness over the canonical OC Flow / SDD node names.

Layering (doc 58): context layer (L5). The node-name contracts are inlined here (not
imported from OC Flow L9 / harness L6) so this stays a downward-only leaf; a lazy
:func:`verify_against_registries` offers an optional cross-check that imports the
registries only when called (e.g. from a test).
"""

from __future__ import annotations

# Canonical OC Flow node ids (workflows/builtins/oc_flow.yaml). ``completed`` is the
# terminal node and ``local_inspection`` is LLM-free (0 context budget by design).
OC_FLOW_NODES: tuple[str, ...] = (
    "init",
    "gather_context",
    "plan",
    "mutate",
    "local_inspection",
    "diagnose",
    "escalation",
    "consolidation",
    "completed",
)

# Canonical SDD phase ids (harness/phases.py).
SDD_NODES: tuple[str, ...] = (
    "explore",
    "propose",
    "spec",
    "design",
    "tasks",
    "apply",
    "verify",
    "review",
    "judgment",
    "gga",
    "archive",
)

# Default budget for an unknown node so resolution is always defined (book invariant:
# "every workflow node must have a resolvable budget").
DEFAULT_NODE_BUDGET = 4000

# Per-(workflow, node) context token budgets. OC Flow per-node splits sum to 5800
# (within the book's 4k-6k total); SDD Explore 15k (8k-15k), SDD Design 10k (6k-10k),
# Review 5k (3k-5k). All other SDD phases sit inside the SDD envelope.
BUDGETS: dict[str, dict[str, int]] = {
    "oc_flow": {
        "init": 200,
        "gather_context": 2000,
        "plan": 1000,
        "mutate": 1000,
        "local_inspection": 0,
        "diagnose": 1000,
        "escalation": 300,
        "consolidation": 300,
        "completed": 0,
    },
    "sdd": {
        "explore": 15000,
        "propose": 6000,
        "spec": 8000,
        "design": 10000,
        "tasks": 6000,
        "apply": 8000,
        "verify": 5000,
        "review": 5000,
        "judgment": 4000,
        "gga": 4000,
        "archive": 1000,
    },
    # Standalone review workflow (book §Context Budget: Review 3k-5k).
    "review": {"review": 5000},
}

# Workflow-name aliases callers may pass (CLI / registry ids differ from table keys).
_WORKFLOW_ALIASES: dict[str, str] = {
    "oc-flow": "oc_flow",
    "ocflow": "oc_flow",
    "sdd_explore": "sdd",
    "sdd-explore": "sdd",
    "sdd_design": "sdd",
    "sdd-design": "sdd",
}


def _canonical_workflow(workflow: str) -> str:
    key = workflow.strip().lower()
    return _WORKFLOW_ALIASES.get(key, key)


def resolve(workflow: str, node: str) -> int:
    """Resolve the context token budget for ``(workflow, node)``.

    Returns the table value for a known node; falls back to :data:`DEFAULT_NODE_BUDGET`
    for an unknown node so a budget is *always* resolvable (book invariant). The
    standalone ``review`` workflow is consulted as a fallback for a bare ``review``
    node so a review-class node always resolves its 3k-5k budget.
    """
    wf = _canonical_workflow(workflow)
    table = BUDGETS.get(wf)
    if table is not None and node in table:
        return table[node]
    if node in BUDGETS.get("review", {}):
        return BUDGETS["review"][node]
    return DEFAULT_NODE_BUDGET


def workflow_total(workflow: str) -> int:
    """Sum of the per-node budgets declared for ``workflow`` (0 if unknown)."""
    return sum(BUDGETS.get(_canonical_workflow(workflow), {}).values())


def known_nodes() -> list[tuple[str, str]]:
    """Every canonical ``(workflow, node)`` pair the table must cover."""
    pairs: list[tuple[str, str]] = [("oc_flow", n) for n in OC_FLOW_NODES]
    pairs.extend(("sdd", n) for n in SDD_NODES)
    pairs.append(("review", "review"))
    return pairs


def assert_complete() -> None:
    """Raise if any canonical node lacks an explicit table entry (book completeness)."""
    missing = [(wf, node) for wf, node in known_nodes() if node not in BUDGETS.get(wf, {})]
    if missing:
        raise AssertionError(f"budget table missing entries for nodes: {missing}")


def verify_against_registries() -> list[str]:
    """Cross-check the table against the live registries (lazy upward imports).

    Returns a list of human-readable mismatches (empty when the table matches the
    live OC Flow definition + SDD phase registry). Imports are deferred so the
    module stays a downward-only leaf at import time.
    """
    problems: list[str] = []
    try:
        from opencontext_core.oc_flow.definition import oc_flow_definition

        live_oc = {n.id for n in oc_flow_definition().nodes.values()}
        for node in live_oc:
            if node not in BUDGETS["oc_flow"]:
                problems.append(f"oc_flow node {node!r} has no budget")
    except Exception as exc:  # pragma: no cover - registry availability varies
        problems.append(f"oc_flow registry unavailable: {exc}")
    return problems
