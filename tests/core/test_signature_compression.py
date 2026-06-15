"""Tests for signature-level code compression."""

from __future__ import annotations

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.context.compression import CompressionEngine
from opencontext_core.context.signature_compression import SignatureCompressor
from opencontext_core.models.context import (
    CompressionStrategy,
    ContextItem,
    ContextPriority,
)

PYTHON_SOURCE = '''\
def authenticate(user: str, password: str) -> bool:
    """Authenticate the user credentials.

    A longer body that should be elided entirely by signature compression.
    """
    record = lookup(user)
    if record is None:
        return False
    return verify(record, password)


class AuthService:
    """Coordinates authentication."""

    def login(self, user: str) -> bool:
        token = self._issue(user)
        return bool(token)
'''


def test_strategy_enum_has_signature() -> None:
    assert CompressionStrategy.SIGNATURE == "signature"


def test_keeps_signature_and_drops_body() -> None:
    compressor = SignatureCompressor()
    result = compressor.compress(PYTHON_SOURCE, language="python")

    # Signatures are preserved.
    assert "def authenticate(user: str, password: str) -> bool:" in result
    assert "class AuthService:" in result
    assert "def login(self, user: str) -> bool:" in result
    # The first docstring line is kept.
    assert "Authenticate the user credentials." in result
    # Body statements are removed.
    assert "record = lookup(user)" not in result
    assert "return verify(record, password)" not in result
    assert "token = self._issue(user)" not in result
    # Compression reduced the size.
    assert len(result) < len(PYTHON_SOURCE)


def test_regex_fallback_for_unsupported_language() -> None:
    compressor = SignatureCompressor()
    # An unknown language forces the regex fallback path for python-shaped code.
    result = compressor.compress(PYTHON_SOURCE, language="unsupported-lang")

    assert "def authenticate(user: str, password: str) -> bool:" in result
    assert "record = lookup(user)" not in result
    assert len(result) < len(PYTHON_SOURCE)


def test_handles_fenced_code_blocks_and_preserves_prose() -> None:
    compressor = SignatureCompressor()
    text = (
        "Here is the function:\n\n"
        "```python\n" + PYTHON_SOURCE + "```\n\n"
        "That concludes the explanation."
    )
    result = compressor.compress(text)

    assert "Here is the function:" in result
    assert "That concludes the explanation." in result
    assert "def authenticate(user: str, password: str) -> bool:" in result
    assert "record = lookup(user)" not in result


def test_engine_signature_strategy_reduces_tokens() -> None:
    config = OpenContextConfig.model_validate(default_config_data())
    compression = config.context.compression.model_copy(
        update={"strategy": CompressionStrategy.SIGNATURE, "protected_spans": False}
    )
    engine = CompressionEngine(compression)
    item = ContextItem(
        id="auth",
        content=PYTHON_SOURCE,
        source="src/auth.py",
        source_type="file",
        priority=ContextPriority.P3,
        tokens=200,
        score=0.5,
    )

    result = engine.compress_item(item)

    assert result.strategy is CompressionStrategy.SIGNATURE
    assert result.item.metadata["compression"]["strategy"] == "signature"
    assert "def authenticate(user: str, password: str) -> bool:" in result.item.content
    assert "record = lookup(user)" not in result.item.content
    assert result.compressed_tokens <= result.original_tokens


def test_empty_input_returns_empty() -> None:
    assert SignatureCompressor().compress("") == ""
