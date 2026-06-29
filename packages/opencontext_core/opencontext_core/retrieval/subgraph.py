"""Budgeted KG context subgraph (PR-008, KG-11; OC-KG-001 §18-19).

``ContextSubgraph`` is the typed result of KG-backed retrieval: the selected typed
nodes/edges plus their evidence, the omissions (with reasons), a token estimate, and
a normalized confidence. Unlike the flat ``EvidencePlan`` (which the planner still
produces), the subgraph enforces BOTH a token budget and a node-count budget and
carries the typed v2 schema.

Layering (doc 58): retrieval/Context layer (L5). It composes L0 KG v2 models and a
context-budgeting helper; it does not reach back into the KG L4 substrate.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.models.evidence import EvidenceRef
from opencontext_core.models.kg_v2 import KgEdge, KgNode


class Omission(BaseModel):
    """A node dropped from the subgraph, with a deterministic reason."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(description="Id of the omitted node.")
    name: str = Field(default="", description="Name of the omitted node.")
    reason: str = Field(description="Why it was omitted (node_budget/token_budget/...).")


class ContextSubgraph(BaseModel):
    """A budgeted, typed, evidence-backed subgraph for a task (OC-KG-001 §18)."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[KgNode] = Field(default_factory=list, description="Selected typed nodes.")
    edges: list[KgEdge] = Field(default_factory=list, description="Selected typed edges.")
    evidence: list[EvidenceRef] = Field(
        default_factory=list, description="Evidence backing the subgraph."
    )
    omitted: list[Omission] = Field(
        default_factory=list, description="Nodes dropped under budget, with reasons."
    )
    token_estimate: int = Field(default=0, ge=0, description="Estimated token cost of the nodes.")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Subgraph confidence [0,1].")


def _node_tokens(node: KgNode) -> int:
    """Deterministic token estimate for a node's renderable surface."""
    signature = str(node.properties.get("signature") or "")
    text = f"{node.type.value} {node.name} {node.path or ''} {signature}"
    return estimate_tokens(text)


def _confidence(
    selected: list[KgNode],
    omitted: list[Omission],
    *,
    exact_match: bool,
    tests_found: bool,
    owners_found: bool,
    fresh: bool,
) -> float:
    """Compute a normalized subgraph confidence from book §19 signals.

    Blends the mean per-node confidence with structural signals (exact symbol
    match, matching tests, owners present, graph freshness) and penalizes missing
    links (omissions) and stale nodes. Bounded to [0,1]. Empty selection => 0.0.
    """
    if not selected:
        return 0.0
    node_conf = sum(n.temporal.confidence for n in selected) / len(selected)
    stale = sum(1 for n in selected if n.temporal.status != "active")
    stale_penalty = stale / len(selected)
    missing_penalty = min(0.2, 0.05 * len(omitted))

    score = 0.5 * node_conf
    score += 0.15 if exact_match else 0.0
    score += 0.1 if tests_found else 0.0
    score += 0.1 if owners_found else 0.0
    score += 0.15 if fresh else 0.0
    score -= 0.2 * stale_penalty
    score -= missing_penalty
    return max(0.0, min(1.0, score))


def build_context_subgraph(
    nodes: list[KgNode],
    *,
    max_nodes: int,
    max_tokens: int,
    edges: list[KgEdge] | None = None,
    exact_match: bool = False,
    tests_found: bool = False,
    owners_found: bool = False,
    fresh: bool = True,
) -> ContextSubgraph:
    """Select ``nodes`` into a :class:`ContextSubgraph` under node + token budgets.

    ``nodes`` must already be relevance-ranked (best first). Selection stops at the
    first budget hit; every remaining candidate is recorded as an :class:`Omission`
    naming which budget it breached. Only edges between selected nodes are kept, and
    their evidence (plus node evidence) is aggregated. Confidence is computed from
    the §19 signals over the selected set.
    """
    selected: list[KgNode] = []
    omitted: list[Omission] = []
    token_total = 0

    for node in nodes:
        if len(selected) >= max_nodes:
            omitted.append(Omission(node_id=node.id, name=node.name, reason="node_budget"))
            continue
        cost = _node_tokens(node)
        if token_total + cost > max_tokens and selected:
            omitted.append(Omission(node_id=node.id, name=node.name, reason="token_budget"))
            continue
        selected.append(node)
        token_total += cost

    selected_ids = {n.id for n in selected}
    kept_edges = [
        e for e in (edges or []) if e.source_id in selected_ids and e.target_id in selected_ids
    ]

    evidence: list[EvidenceRef] = []
    for node in selected:
        evidence.extend(node.evidence)
    for edge in kept_edges:
        evidence.extend(edge.evidence)

    confidence = _confidence(
        selected,
        omitted,
        exact_match=exact_match,
        tests_found=tests_found,
        owners_found=owners_found,
        fresh=fresh,
    )
    return ContextSubgraph(
        nodes=selected,
        edges=kept_edges,
        evidence=evidence,
        omitted=omitted,
        token_estimate=token_total,
        confidence=confidence,
    )
