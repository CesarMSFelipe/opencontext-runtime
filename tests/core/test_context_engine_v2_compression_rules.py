"""PR-010 SPEC-CTX-010-12: codified semantic-compression priority rules."""

from __future__ import annotations

from opencontext_core.config import CompressionConfig, CompressionStrategy
from opencontext_core.context.compression import (
    COMPRESS_KINDS,
    DISCARD_KINDS,
    KEEP_KINDS,
    CompressionEngine,
    compression_priority,
)
from opencontext_core.context.gc import compact_l1
from opencontext_core.context.protection import ProtectedSpanManager
from opencontext_core.models.context import ContextItem, ContextPriority


def test_priority_taxonomy_is_codified() -> None:
    assert "acceptance_criteria" in KEEP_KINDS
    assert "signature" in KEEP_KINDS
    assert "diagnostic" in KEEP_KINDS
    assert "evidence" in KEEP_KINDS
    assert "repeated_log" in COMPRESS_KINDS
    assert "obsolete_reasoning" in DISCARD_KINDS


def test_compression_priority_classifies_each_bucket() -> None:
    assert compression_priority("acceptance_criteria") == "keep"
    assert compression_priority("constraint") == "keep"
    assert compression_priority("repeated_log") == "compress"
    assert compression_priority("obsolete_reasoning") == "discard"
    assert compression_priority("anything_else") == "compress"  # safe default


def test_semantic_keep_spans_detected() -> None:
    mgr = ProtectedSpanManager()
    ac = "GIVEN a user\nWHEN they log in\nTHEN a token is issued"
    assert any(s.kind == "acceptance_criteria" for s in mgr.detect_semantic_keep(ac))
    diag = "Traceback (most recent call last)\nValueError: boom"
    assert any(s.kind == "diagnostic" for s in mgr.detect_semantic_keep(diag))
    sig = "def transfer(amount: int) -> bool:"
    assert any(s.kind == "signature" for s in mgr.detect_semantic_keep(sig))


def _engine(strategy: CompressionStrategy = CompressionStrategy.TRUNCATE) -> CompressionEngine:
    cfg = CompressionConfig(
        enabled=True,
        strategy=strategy,
        adaptive=False,
        protected_spans=True,
        max_compression_ratio=0.3,
    )
    return CompressionEngine(cfg, semantic_protection=True)


def _item(content: str) -> ContextItem:
    return ContextItem(
        id="x",
        content=content,
        source="notes.md",
        source_type="file",
        priority=ContextPriority.P3,
        tokens=400,
        score=0.5,
    )


def test_acceptance_criteria_preserved_while_logs_are_crushed() -> None:
    # Acceptance criteria mixed in -> the item is KEPT verbatim under semantic rules.
    ac_content = ("padding text. " * 40) + "\nAC1: the API must validate the token first\n"
    kept = _engine().compress_item(_item(ac_content))
    assert kept.item.content == ac_content
    assert kept.item.metadata["compression"]["reason"] == "protected_spans_detected"

    # Repeated logs with no KEEP span -> compressed (smaller).
    logs = "INFO request received\n" * 60
    crushed = _engine().compress_item(_item(logs))
    assert crushed.compressed_tokens < crushed.original_tokens


def test_legacy_compression_unchanged_without_semantic_protection() -> None:
    # Default engine (semantic_protection off) still compresses code with signatures.
    cfg = CompressionConfig(
        enabled=True,
        strategy=CompressionStrategy.TRUNCATE,
        adaptive=False,
        protected_spans=True,
        max_compression_ratio=0.3,
    )
    engine = CompressionEngine(cfg)  # semantic_protection defaults False
    # No numbers/paths so the legacy detector finds no spans; the signature alone
    # must NOT block compression when semantic protection is off.
    code = "def foo():\n    return value\n" + ("filler prose line here\n" * 60)
    result = engine.compress_item(_item(code))
    assert result.compressed_tokens < result.original_tokens


def test_gc_discards_obsolete_reasoning_and_keeps_diagnostics() -> None:
    l1 = {
        "diagnostics": "current failure",
        "obsolete_reasoning": "old wrong idea",
        "logs": ["a", "a", "b"],
    }
    compacted, discarded = compact_l1(l1)
    assert "obsolete_reasoning" in discarded
    assert "obsolete_reasoning" not in compacted
    assert compacted["diagnostics"] == "current failure"  # KEEP survives
