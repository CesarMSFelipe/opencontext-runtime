"""Tests for TerseCompressionBackend."""

from opencontext_core.backends.compression.terse import TerseCompressionBackend
from opencontext_core.models.context import ProtectedSpan


def test_terse_reduces_length():
    backend = TerseCompressionBackend()
    # Use repeated hedging words that terse definitely strips at word level via phrase compression
    text = (
        "In order to do this, and due to the fact that there are many cases, "
        "we should in order to proceed handle it. "
        * 5
    )
    result = backend.compress(text, [])
    assert len(result) < len(text)


def test_terse_protected_span_content_preserved():
    backend = TerseCompressionBackend()
    protected_text = "SECRET_TOKEN_abc123"
    text = f"Some prose before. {protected_text} Some prose after."
    start = text.index(protected_text)
    end = start + len(protected_text)
    spans = [ProtectedSpan(start=start, end=end, kind="token", content=protected_text)]
    result = backend.compress(text, spans)
    assert protected_text in result


def test_terse_name():
    assert TerseCompressionBackend.name == "terse"


def test_terse_empty_text_returns_empty():
    backend = TerseCompressionBackend()
    assert backend.compress("", []) == ""
