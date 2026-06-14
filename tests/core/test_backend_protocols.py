"""Tests for backend protocols and NullCompressionBackend."""

from opencontext_core.backends.compression.null import NullCompressionBackend
from opencontext_core.backends.protocols import CompressionBackend, VectorBackend
from opencontext_core.backends.vector.null import NullVectorBackend


def test_compression_backend_is_runtime_checkable():
    backend = NullCompressionBackend()
    assert isinstance(backend, CompressionBackend)


def test_vector_backend_is_runtime_checkable():
    backend = NullVectorBackend()
    assert isinstance(backend, VectorBackend)


def test_null_compression_backend_returns_input_unchanged():
    backend = NullCompressionBackend()
    text = "Hello, world! This is a test."
    assert backend.compress(text, []) == text


def test_null_compression_backend_name():
    assert NullCompressionBackend.name == "null"
