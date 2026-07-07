"""Public source-id contract for pack items.

Pack items may carry chunk-suffixed sources internally (graph symbols use
``path:line``), but every public surface that reports *sources* — the API's
``included_sources``, trace ``quality_inputs``, harness provenance gates —
must report unique bare file paths. ``ContextItem.source_path`` is the single
normalization point and ``unique_source_paths`` the deduping projection; this
module pins both so chunk ids can never leak into the public contract again.
"""

from __future__ import annotations

from opencontext_core.models.context import (
    ContextItem,
    ContextPriority,
    unique_source_paths,
)


def _item(source: str, *, source_type: str = "file", **metadata: object) -> ContextItem:
    return ContextItem(
        id=f"id:{source}",
        content="body",
        source=source,
        source_type=source_type,
        priority=ContextPriority.P1,
        tokens=4,
        score=1.0,
        metadata=dict(metadata) if metadata else {},
    )


class TestSourcePath:
    def test_plain_file_source_is_unchanged(self) -> None:
        assert _item("src/auth.py").source_path == "src/auth.py"

    def test_graph_symbol_prefers_provenance_file_path(self) -> None:
        item = _item(
            "src/auth.py:2",
            source_type="graph_symbol",
            graph_provenance={"file_path": "src/auth.py", "line": 2},
        )
        assert item.source_path == "src/auth.py"

    def test_chunk_line_suffix_is_stripped_without_provenance(self) -> None:
        assert _item("src/auth.py:17", source_type="graph_symbol").source_path == "src/auth.py"

    def test_memory_key_is_not_mangled(self) -> None:
        item = _item("memory:decisions/auth-model", source_type="memory")
        assert item.source_path == "memory:decisions/auth-model"


class TestUniqueSourcePaths:
    def test_chunks_of_one_file_dedupe_to_bare_path_in_order(self) -> None:
        items = [
            _item("src/auth.py:1", source_type="graph_symbol"),
            _item("src/auth.py:2", source_type="graph_symbol"),
            _item("README.md"),
        ]
        assert unique_source_paths(items) == ["src/auth.py", "README.md"]

    def test_empty_items_yield_empty_list(self) -> None:
        assert unique_source_paths([]) == []
