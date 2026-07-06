"""KG-PACK-CONTRACT: the pack metrics block carries the plan's kg fields.

The plan's nested ``kg`` block maps onto the flat contract metrics:
``used`` -> kg_used, ``nodes_selected`` -> kg_nodes_used, ``edges_used`` ->
kg_edges_used, ``test_nodes_included`` -> test_nodes_included, ``reason`` ->
kg_reason. Assertions here are value-level (real counts, not key presence).
"""

from __future__ import annotations

from opencontext_core.context.packing import ContextPackBuilder, build_pack_metrics
from opencontext_core.models.context import ContextItem, ContextPackMetrics, ContextPriority


def _item(
    item_id: str,
    source: str,
    *,
    tokens: int = 20,
    score: float = 0.8,
    source_type: str = "file",
    metadata: dict | None = None,
) -> ContextItem:
    return ContextItem(
        id=item_id,
        content=f"content of {item_id}",
        source=source,
        source_type=source_type,
        priority=ContextPriority.P1,
        tokens=tokens,
        score=score,
        metadata=metadata or {},
    )


def _graph_item(
    item_id: str, source: str, relationships: list[str], *, score: float = 0.9
) -> ContextItem:
    return _item(
        item_id,
        source,
        source_type="graph_symbol",
        score=score,
        metadata={
            "retrieval_source": "graph",
            "graph_provenance": {
                "file_path": source,
                "line": 3,
                "relationships": relationships,
            },
        },
    )


def _metrics(items: list[ContextItem]) -> ContextPackMetrics:
    result = ContextPackBuilder().pack(items, available_tokens=1000)
    return build_pack_metrics(result, candidates=items)


def test_pack_metrics_count_kg_test_nodes_and_edges() -> None:
    """KG-PACK-CONTRACT: test_nodes_included and kg_edges_used report real counts."""
    items = [
        _graph_item("graph:calc.py:3:multiply", "calc.py:3", ["called_by:test_multiply"]),
        _graph_item(
            "graph:tests/test_calc.py:5:test_multiply",
            "tests/test_calc.py:5",
            ["calls:multiply"],
        ),
        _item("readme", "README.md"),
    ]
    metrics = _metrics(items)
    assert metrics.kg_used is True
    assert metrics.kg_nodes_used == 2
    assert metrics.kg_edges_used == 2
    assert metrics.test_nodes_included == 1


def test_pack_metrics_kg_reason_reflects_selection() -> None:
    """KG-PACK-CONTRACT: kg_reason is a non-empty pack-level rationale when KG was used."""
    items = [_graph_item("graph:calc.py:3:multiply", "calc.py:3", ["called_by:test_multiply"])]
    metrics = _metrics(items)
    assert isinstance(metrics.kg_reason, str)
    assert metrics.kg_reason
    assert "graph" in metrics.kg_reason.lower()


def test_pack_metrics_kg_fields_without_graph_items() -> None:
    """KG-PACK-CONTRACT: without KG items the kg fields honestly report non-use."""
    metrics = _metrics([_item("readme", "README.md")])
    assert metrics.kg_used is False
    assert metrics.test_nodes_included == 0
    assert isinstance(metrics.kg_reason, str)
    assert "no " in metrics.kg_reason.lower()


def test_pack_metrics_serialize_kg_fields_additively() -> None:
    """KG-PACK-CONTRACT: metrics JSON carries the kg block fields alongside frozen keys."""
    items = [_graph_item("graph:calc.py:3:multiply", "calc.py:3", ["called_by:test_multiply"])]
    dumped = _metrics(items).model_dump()
    for key in (
        "kg_used",
        "kg_nodes_used",
        "kg_edges_used",
        "test_nodes_included",
        "kg_reason",
    ):
        assert key in dumped, f"missing kg contract field: {key}"


def test_pack_metrics_model_tolerates_legacy_payloads_without_new_fields() -> None:
    """KG-PACK-CONTRACT: persisted metrics without the new fields still validate (additive)."""
    legacy = {
        "budget_tokens": 800,
        "input_tokens_estimated": 900,
        "output_tokens_estimated": 100,
        "compression_ratio": None,
        "kg_used": False,
        "kg_nodes_used": 0,
        "kg_edges_used": 0,
        "memory_hits": 0,
        "protected_spans": 0,
        "protected_spans_kept": 0,
        "excluded_files": 0,
    }
    metrics = ContextPackMetrics.model_validate(legacy)
    assert metrics.test_nodes_included == 0
    assert metrics.kg_reason is None
