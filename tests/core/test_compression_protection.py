"""Inline constraint protection + budget-clamp lossiness guard.

Covers two gaps in safe compression:

1. ``ProtectedSpanManager.detect`` previously only matched warning/constraint
   triggers that were anchored to the START of a line, so a load-bearing
   constraint embedded mid-paragraph ("the API must never be called twice")
   was NOT protected and the default EXTRACTIVE_HEAD_TAIL strategy could drop
   it (it keeps head + tail, cuts the middle).
2. There was no lossiness guard: when a budget clamp keeps only the head of an
   item, a protected span past the cut point was silently dropped.
"""

from __future__ import annotations

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.context.compression import CompressionEngine
from opencontext_core.context.protection import ProtectedSpanManager
from opencontext_core.models.context import ContextItem, ContextPriority


def _engine() -> CompressionEngine:
    return CompressionEngine(
        OpenContextConfig.model_validate(default_config_data()).context.compression
    )


def _context(content: str, tokens: int = 500) -> ContextItem:
    return ContextItem(
        id="constraint",
        content=content,
        source="docs/api.md",
        source_type="file",
        priority=ContextPriority.P3,
        tokens=tokens,
        score=0.5,
    )


# A long prose item whose ONLY protected content is an inline constraint sitting
# squarely in the middle -- exactly where head/tail extraction would cut.
_HEAD = "Background prose about the request pipeline. " * 12
_TAIL = "Further unrelated trailing prose about logging and retries. " * 12
_INLINE = "Importantly, the authentication endpoint must never be called twice per session. "
_MIDDLE_CONSTRAINT = _HEAD + _INLINE + _TAIL


def test_inline_must_never_is_detected_as_protected() -> None:
    """(a) An inline 'must never ...' mid-paragraph is now DETECTED as protected."""

    spans = ProtectedSpanManager().detect(_MIDDLE_CONSTRAINT)

    warning_spans = [span for span in spans if span.kind == "warning"]
    assert warning_spans, "inline constraint trigger should be detected as a warning span"

    span = warning_spans[0]
    assert "must never" in span.content.lower()
    # The constraint sits in the middle of the text, well past the head region.
    head_len = len(_HEAD)
    assert span.start >= head_len


def test_item_with_inline_constraint_is_returned_uncompressed() -> None:
    """(b) An item with such a span is returned uncompressed (not middle-cut)."""

    item = _context(_MIDDLE_CONSTRAINT, tokens=500)
    # Force the over-budget extractive path: target would otherwise drop the middle.
    result = _engine().compress_item(item)

    # Content is preserved verbatim -- the middle constraint is intact.
    assert result.item.content == _MIDDLE_CONSTRAINT
    assert "must never be called twice" in result.item.content
    assert result.item.metadata["compression"]["reason"] == "protected_spans_detected"
    assert result.item.metadata["compression"]["lossiness"] == "none"


def test_extractive_head_tail_would_drop_middle_without_protection() -> None:
    """Sanity check: without protection the same content loses its middle constraint.

    This proves the protection above is load-bearing, not incidental.
    """

    from opencontext_core.config import CompressionConfig, CompressionStrategy

    config = CompressionConfig(
        enabled=True,
        strategy=CompressionStrategy.EXTRACTIVE_HEAD_TAIL,
        adaptive=False,
        protected_spans=False,  # disable the guard
        max_compression_ratio=0.3,
    )
    result = CompressionEngine(config).compress_item(_context(_MIDDLE_CONSTRAINT, tokens=500))

    # With protection off, the middle (the constraint) is cut by head/tail extraction.
    assert "must never be called twice" not in result.item.content
    assert "[... lossy excerpt ...]" in result.item.content


def test_ordinary_prose_is_not_falsely_protected() -> None:
    """Whole-word matching must not fire on substrings like 'nevertheless'."""

    text = "Nevertheless the requirements were unclear, so a reformed plan emerged later."
    warning_spans = [s for s in ProtectedSpanManager().detect(text) if s.kind == "warning"]
    assert warning_spans == []


def test_budget_clamp_records_dropped_protected_span() -> None:
    """Lossiness guard: a head-only budget clamp records the dropped protected span.

    When protected_spans is disabled the constraint reaches compress_items and a
    tight budget clamps to the head only -- the trailing constraint must be
    recorded as omitted rather than silently cut.
    """

    from opencontext_core.config import CompressionConfig, CompressionStrategy

    config = CompressionConfig(
        enabled=True,
        strategy=CompressionStrategy.NONE,  # no per-item compression; force budget clamp only
        adaptive=False,
        protected_spans=False,
        max_compression_ratio=0.5,
    )
    engine = CompressionEngine(config)

    # Constraint is in the tail so a head-only clamp drops it.
    content = ("Plain leading prose. " * 30) + "You must not delete the audit log."
    item = _context(content, tokens=200)

    _items, results = engine.compress_items([item], budget_tokens=20)
    clamp = results[0]
    meta = clamp.item.metadata["compression"]

    assert meta.get("budget_clamped") is True
    omitted = meta.get("omitted_protected_spans")
    assert omitted, "dropped protected span should be recorded, not silently cut"
    assert any("must not" in span["content"].lower() for span in omitted)
    assert meta["lossiness"] == "lossy_budget_clamp_protected"
