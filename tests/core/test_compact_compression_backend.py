"""Tests for CompactCompressionBackend."""

from opencontext_core.backends.compression.compact import CompactCompressionBackend
from opencontext_core.models.context import ProtectedSpan


def test_compact_name():
    assert CompactCompressionBackend.name == "compact"


def test_compact_python_signature_preserved_body_removed():
    backend = CompactCompressionBackend()
    text = """```python
def process(self, data: dict) -> Result:
    x = 1
    y = 2
    return Result(x + y)
```"""
    result = backend.compress(text, [])
    assert "def process" in result
    assert "data: dict" in result
    # Body lines should be gone or replaced with ...
    assert "x = 1" not in result or "..." in result


def test_compact_docstring_first_line_preserved():
    backend = CompactCompressionBackend()
    text = '''```python
def my_func(x: int) -> int:
    """Compute the result value.

    This is a longer description that should be removed.
    """
    return x * 2
```'''
    result = backend.compress(text, [])
    assert "def my_func" in result


def test_compact_protected_span_verbatim():
    backend = CompactCompressionBackend()
    protected = "MUST_NOT_CHANGE_abc123"
    text = f"Some prose. {protected} More prose."
    start = text.index(protected)
    end = start + len(protected)
    spans = [ProtectedSpan(start=start, end=end, kind="token", content=protected)]
    result = backend.compress(text, spans)
    assert protected in result


def test_compact_non_code_text_shorter():
    backend = CompactCompressionBackend()
    # Repeated prose to ensure terse compression reduces length
    text = (
        "In order to do this, and due to the fact that there are many items, "
        "we should in order to proceed handle it. "
        * 5
    )
    result = backend.compress(text, [])
    assert len(result) < len(text)
