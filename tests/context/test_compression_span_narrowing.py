"""Protected-span narrowing: only LOAD-BEARING spans block compression.

Regression for a validation finding: the compression engine bailed out (returned
the item verbatim) whenever ANY protected span was detected. `numeric_value` and
`file_path` fire on virtually every real code/text item, so compression NEVER ran
on real content — savings came only from selection. The narrowing lets compression
proceed when the only spans are trivial (numbers/paths) while still preserving
warnings, constraints, schemas, code blocks, citations, and semantic-KEEP spans.
"""

from __future__ import annotations

from types import SimpleNamespace

from opencontext_core.config import CompressionConfig
from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.context.compression import CompressionEngine
from opencontext_core.context.packing import ContextPackBuilder
from opencontext_core.models.context import ContextItem


def _item(content: str) -> ContextItem:
    return ContextItem(
        id="i",
        source="graph:i",
        source_type="graph",
        content=content,
        score=0.9,
        tokens=estimate_tokens(content),
        priority=2,
    )


def _reason(result) -> str | None:
    return result.item.metadata.get("compression", {}).get("reason")


def test_load_bearing_warning_still_preserved_verbatim() -> None:
    """A 'must never' constraint blocks lossy compression (preserved verbatim)."""
    eng = CompressionEngine(CompressionConfig())  # protected_spans=True (default)
    content = "Handle the batch.\n# WARNING: this endpoint must never be called twice.\n"
    result = eng.compress_item(_item(content))
    assert _reason(result) == "protected_spans_detected"
    assert "must never" in result.item.content


def test_trivial_only_spans_no_longer_block_compression() -> None:
    """Content whose only spans are numbers/paths is NOT auto-preserved.

    Before the fix any digit or import path triggered protected_spans_detected and
    compression never ran. Now that reason must NOT be emitted for trivial-only
    content, so a lossy strategy is free to run.
    """
    eng = CompressionEngine(CompressionConfig())
    content = "value = lib/util.py offset 42 plus 1024 tokens\n" * 20
    result = eng.compress_item(_item(content))
    assert _reason(result) != "protected_spans_detected"


class _ShrinkEngine:
    """A compression engine stub that always shrinks an item to fit."""

    def compress_item(self, item: ContextItem):
        return SimpleNamespace(item=item.model_copy(update={"content": "…", "tokens": 10}))


def test_over_budget_item_is_compressed_not_omitted() -> None:
    """A single item larger than the whole budget is compressed to fit, not dropped.

    Regression: the packer omitted an over-budget span (used_tokens=0) BEFORE the
    compression branch, so an over-budget function yielded zero content instead of
    a compressed version.
    """
    big = _item("x" * 4000)
    big = big.model_copy(update={"tokens": 800})  # exceeds the 200 budget
    builder = ContextPackBuilder()

    # No engine: unchanged behaviour — omitted.
    no_engine = builder.pack([big], available_tokens=200)
    assert len(no_engine.included) == 0
    assert len(no_engine.omitted) == 1

    # With an engine that shrinks it: included as compressed, not omitted.
    with_engine = builder.pack([big], available_tokens=200, compression_engine=_ShrinkEngine())
    assert len(with_engine.included) == 1
    assert with_engine.used_tokens == 10
    assert with_engine.omitted == []
    assert with_engine.compression is not None and with_engine.compression.items_compressed == 1
