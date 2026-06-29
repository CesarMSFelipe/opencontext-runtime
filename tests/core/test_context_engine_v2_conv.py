"""PR-010 Phase CONV: semantic cache, routing, usefulness, full-file reason, wiring."""

from __future__ import annotations

from opencontext_core.cache.base import build_cache_key
from opencontext_core.cache.semantic_cache import LocalSemanticCache
from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.context.compression import CompressionEngine
from opencontext_core.context.engine import (
    ContextEngine,
    envelope_l3_from_subgraph,
    to_surgical_envelope,
)
from opencontext_core.context.strategies import select_strategy
from opencontext_core.models.context import ContextItem, ContextPriority, RetrievalStrategy


def _engine(cache: LocalSemanticCache | None = None) -> ContextEngine:
    cfg = OpenContextConfig.model_validate(default_config_data())
    comp = CompressionEngine(cfg.context.compression, semantic_protection=True)
    return ContextEngine(compression_engine=comp, semantic_cache=cache)


def _item(item_id: str, source_type: str = "file", tokens: int = 30) -> ContextItem:
    return ContextItem(
        id=item_id,
        content=f"body {item_id} " * 3,
        source=f"{item_id}.py",
        source_type=source_type,
        priority=ContextPriority.P2,
        tokens=tokens,
        score=0.7,
    )


# --- CONV: semantic cache --------------------------------------------------------
def test_similar_task_hits_semantic_cache_with_provenance() -> None:
    cache = LocalSemanticCache(similarity_threshold=0.5, require_same_project_hash=False)
    key = build_cache_key(
        workflow_name="oc_flow",
        project_hash="h",
        model_name="m",
        prompt_version="v",
        user_input="u",
        context="c",
    )
    eng = _engine(cache)
    first = eng.build(
        "oc_flow",
        "gather_context",
        "add login token validation flow",
        candidates=[_item("a")],
        cache_key=key,
    )
    assert first.cache_hit is False
    second = eng.build(
        "oc_flow",
        "gather_context",
        "add login token validation flow now",
        candidates=[_item("a")],
        cache_key=key,
    )
    assert second.cache_hit is True
    assert second.cache_provenance is not None
    assert second.cache_provenance["source"] == "semantic_cache"


# --- CONV: context routing -------------------------------------------------------
def test_verify_node_routes_test_first() -> None:
    assert select_strategy("verify", "") is RetrievalStrategy.TEST_FIRST


# --- CONV: usefulness scoring ----------------------------------------------------
def test_delivered_items_carry_a_usefulness_score() -> None:
    res = _engine().build("oc_flow", "gather_context", "task", candidates=[_item("a")])
    items = res.envelope.l1["items"]
    assert items
    assert all(it["usefulness"] is not None and it["usefulness"] > 0 for it in items)


# --- CONV: full-file inclusion requires a reason ---------------------------------
def test_full_file_inclusion_carries_a_reason() -> None:
    res = _engine().build("oc_flow", "gather_context", "task", candidates=[_item("whole")])
    item = res.envelope.l1["items"][0]
    assert item["full_file_reason"]  # whole-file load has an explicit reason


# --- Reconciliation: one canonical envelope, surgical projection -----------------
def test_canonical_envelope_projects_onto_oc_flow_seam() -> None:
    res = _engine().build("oc_flow", "gather_context", "task", candidates=[_item("a"), _item("b")])
    surgical = to_surgical_envelope(res.envelope)
    assert surgical.task == "task"
    assert surgical.has_items
    assert surgical.token_estimate == res.envelope.token_estimate


# --- KG wiring: L3 from a PR-008 ContextSubgraph --------------------------------
class _Type:
    value = "symbol"


class _Node:
    id = "kg_1"
    name = "BridgeDetector"
    type = _Type()
    path = "src/bridge.py"


class _Sub:
    def __init__(self, nodes: list, confidence: float) -> None:
        self.nodes = nodes
        self.edges: list = []
        self.confidence = confidence


def test_l3_assembled_from_kg_subgraph() -> None:
    # envelope_l3_from_subgraph is duck-typed over the PR-008 ContextSubgraph shape.
    l3 = envelope_l3_from_subgraph(_Sub(nodes=[_Node()], confidence=0.6))
    assert l3["kg_nodes"][0]["name"] == "BridgeDetector"
    assert l3["kg_nodes"][0]["type"] == "symbol"
    assert l3["confidence"] == 0.6
