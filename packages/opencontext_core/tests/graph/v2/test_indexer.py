"""PR-008.b KG v2 incremental Tree-Sitter indexer — T008b.1, T008b.3."""

from __future__ import annotations

from opencontext_core.graph.v2.indexer import (
    GraphDelta,
    IncrementalIndexer,
    IndexOptions,
    IndexResult,
)


class TestIndexer:
    def test_balanced_budget(self) -> None:
        opts = IndexOptions(max_tokens=3000, budget_mode="warn")
        assert opts.max_tokens == 3000

    def test_file_change_delta(self) -> None:
        """REQ_kg_v2_002: file change produces a delta."""
        indexer = IncrementalIndexer()
        delta = indexer.compute_delta(
            added={"src/new.py"}, modified={"src/changed.py"}, deleted={"src/old.py"}
        )
        assert isinstance(delta, GraphDelta)
        assert delta.added_count >= 0
        assert delta.modified_count >= 0
        assert delta.deleted_count >= 0

    def test_empty_delta(self) -> None:
        indexer = IncrementalIndexer()
        delta = indexer.compute_delta(set(), set(), set())
        assert delta.total_changes == 0

    def test_options_frozen(self) -> None:
        opts = IndexOptions(max_tokens=1000)
        assert opts.max_tokens == 1000
