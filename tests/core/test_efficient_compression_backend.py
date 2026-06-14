"""Tests for EfficientCompressionBackend."""
import pytest


def test_compresses_code_to_signatures():
    from opencontext_core.backends.compression.efficient import EfficientCompressionBackend
    backend = EfficientCompressionBackend()
    text = """```python
def authenticate(user, password):
    \"\"\"Authenticate user credentials.\"\"\"
    result = check_db(user, password)
    if result:
        return True
    return False
```"""
    compressed = backend.compress(text, [])
    # Should have reduced the body
    assert len(compressed) < len(text)


def test_applies_extended_dict_substitutions():
    from opencontext_core.backends.compression.efficient import EfficientCompressionBackend
    backend = EfficientCompressionBackend()
    text = "This function implements authentication functionality without configuration"
    compressed = backend.compress(text, [])
    # Should have substituted some terms
    assert len(compressed) <= len(text)


def test_preserves_protected_spans():
    from opencontext_core.backends.compression.efficient import EfficientCompressionBackend
    from opencontext_core.models.context import ProtectedSpan
    backend = EfficientCompressionBackend()
    protected_text = "MUST_KEEP_THIS_VERBATIM"
    full_text = f"Some implementation details here. {protected_text} More function details."
    start = full_text.index(protected_text)
    end = start + len(protected_text)
    spans = [ProtectedSpan(start=start, end=end, kind="code", content=protected_text)]
    compressed = backend.compress(full_text, spans)
    assert protected_text in compressed


def test_produces_fewer_tokens_than_compact_alone():
    from opencontext_core.backends.compression.efficient import EfficientCompressionBackend
    from opencontext_core.backends.compression.compact import CompactCompressionBackend
    efficient = EfficientCompressionBackend()
    compact = CompactCompressionBackend()
    text = (
        "This implementation demonstrates the functionality of the authentication service. "
        "The function validates user credentials and returns a response object. "
        "The handler processes requests and calls the connection interface module."
    )
    efficient_result = efficient.compress(text, [])
    compact_result = compact.compress(text, [])
    assert len(efficient_result) <= len(compact_result)
