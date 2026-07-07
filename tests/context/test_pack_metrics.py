"""Pack metrics block tests (GAP-008, KG_CONTEXT_COMPRESSION_CONTRACT).

The pack JSON gains an additive ``context`` metrics block with budget, token,
KG usage, memory, protected-span, and exclusion counters — plus a short
``reason`` on every included item.
"""

from __future__ import annotations

from opencontext_core.context.packing import ContextPackBuilder, build_pack_metrics
from opencontext_core.models.context import (
    CompressionPackMetadata,
    ContextItem,
    ContextPackResult,
    ContextPriority,
)


def _item(
    item_id: str,
    tokens: int = 20,
    score: float = 0.8,
    source_type: str = "file",
    metadata: dict | None = None,
    content: str | None = None,
) -> ContextItem:
    return ContextItem(
        id=item_id,
        content=content if content is not None else f"content of {item_id}",
        source=f"{item_id}.py",
        source_type=source_type,
        priority=ContextPriority.P1,
        tokens=tokens,
        score=score,
        metadata=metadata or {},
    )


def _pack(items: list[ContextItem], budget: int) -> ContextPackResult:
    return ContextPackBuilder().pack(items, available_tokens=budget)


class TestBuildPackMetrics:
    def test_budget_and_token_estimates(self) -> None:
        items = [_item("a", tokens=30), _item("b", tokens=25), _item("c", tokens=90)]
        result = _pack(items, budget=60)
        metrics = build_pack_metrics(result, candidates=items)

        assert metrics.budget_tokens == 60
        assert metrics.input_tokens_estimated == 145  # all candidates considered
        assert metrics.output_tokens_estimated == result.used_tokens
        assert metrics.output_tokens_estimated <= 60

    def test_compression_ratio_none_when_compression_did_not_run(self) -> None:
        items = [_item("a", tokens=10)]
        result = _pack(items, budget=100)
        assert result.compression is None
        metrics = build_pack_metrics(result, candidates=items)
        assert metrics.compression_ratio is None

    def test_compression_ratio_derived_from_pack_compression_metadata(self) -> None:
        items = [_item("a", tokens=10)]
        result = _pack(items, budget=100).model_copy(
            update={
                "compression": CompressionPackMetadata(
                    enabled=True,
                    tokens_before=200,
                    tokens_after=44,
                    items_compressed=1,
                )
            }
        )
        metrics = build_pack_metrics(result, candidates=items)
        assert metrics.compression_ratio == 0.22

    def test_kg_counters_from_graph_provenance(self) -> None:
        graph_item = _item(
            "graph:calc.py:3:multiply_values",
            source_type="graph_symbol",
            metadata={
                "retrieval_source": "graph",
                "graph_provenance": {
                    "file_path": "calc.py",
                    "line": 3,
                    "relationships": ["calls:helper", "called_by:test_multiply_values"],
                },
            },
        )
        expansion_item = _item(
            "graph:calc.py:9:helper",
            source_type="graph_symbol",
            metadata={"retrieval_source": "graph_expansion"},
        )
        fts_item = _item("fts:abc123", source_type="symbol")
        plain_file = _item("readme")
        items = [graph_item, expansion_item, fts_item, plain_file]
        result = _pack(items, budget=1000)
        metrics = build_pack_metrics(result, candidates=items)

        assert metrics.kg_used is True
        assert metrics.kg_nodes_used == 3  # graph + expansion + fts-backed node
        # Two provenance relationships plus one expansion hop.
        assert metrics.kg_edges_used == 3

    def test_kg_counters_zero_without_graph_items(self) -> None:
        items = [_item("a"), _item("b")]
        result = _pack(items, budget=1000)
        metrics = build_pack_metrics(result, candidates=items)
        assert metrics.kg_used is False
        assert metrics.kg_nodes_used == 0
        assert metrics.kg_edges_used == 0

    def test_memory_hits_counts_memory_sourced_included_items(self) -> None:
        items = [
            _item("m1", source_type="memory"),
            _item("m2", metadata={"retrieval_source": "memory"}),
            _item("f1"),
        ]
        result = _pack(items, budget=1000)
        metrics = build_pack_metrics(result, candidates=items)
        assert metrics.memory_hits == 2

    def test_excluded_files_counts_omissions(self) -> None:
        items = [_item("a", tokens=40, score=0.9), _item("b", tokens=40, score=0.5)]
        result = _pack(items, budget=50)
        assert len(result.omissions) == 1
        metrics = build_pack_metrics(result, candidates=items)
        assert metrics.excluded_files == 1

    def test_protected_spans_detected_and_kept(self) -> None:
        protected_content = "```python\ndef f():\n    return 1\n```"
        items = [_item("a", tokens=20, content=protected_content)]
        result = _pack(items, budget=100)
        metrics = build_pack_metrics(result, candidates=items)
        assert metrics.protected_spans >= 1
        assert metrics.protected_spans_kept == metrics.protected_spans

    def test_protected_spans_kept_drops_when_final_content_lost_spans(self) -> None:
        protected_content = "```python\ndef f():\n    return 1\n```"
        items = [_item("a", tokens=20, content=protected_content)]
        result = _pack(items, budget=100)
        # Simulate a lossy compression that dropped the code block.
        clamped = result.included[0].model_copy(update={"content": "def f - summary"})
        result = result.model_copy(update={"included": [clamped]})
        metrics = build_pack_metrics(result, candidates=items)
        assert metrics.protected_spans_kept < metrics.protected_spans


class TestPackResultAdditiveFields:
    def test_pack_result_serializes_context_and_warnings(self) -> None:
        items = [_item("a")]
        result = _pack(items, budget=100)
        dumped = result.model_dump()
        # Additive fields must exist with safe defaults.
        assert "context" in dumped
        assert dumped["warnings"] == []

    def test_metrics_block_has_all_contract_keys(self) -> None:
        items = [_item("a")]
        result = _pack(items, budget=100)
        metrics = build_pack_metrics(result, candidates=items)
        dumped = result.model_copy(update={"context": metrics}).model_dump()["context"]
        for key in (
            "budget_tokens",
            "input_tokens_estimated",
            "output_tokens_estimated",
            "compression_ratio",
            "kg_used",
            "kg_nodes_used",
            "kg_edges_used",
            "memory_hits",
            "protected_spans",
            "protected_spans_kept",
            "excluded_files",
        ):
            assert key in dumped, f"missing contract metric: {key}"


class TestIncludedItemReasons:
    def test_included_items_carry_short_reason(self) -> None:
        items = [
            _item("a", metadata={"retrieval_source": "graph"}),
            _item("b"),
        ]
        result = _pack(items, budget=1000)
        for item in result.included:
            reason = item.metadata.get("reason")
            assert isinstance(reason, str) and reason, f"included item lacks reason: {item.id}"
        assert "graph" in result.included[0].metadata["reason"]
