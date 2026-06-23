"""Tests for BackendFactory."""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from opencontext_core.backends.compression.compact import CompactCompressionBackend
from opencontext_core.backends.compression.null import NullCompressionBackend
from opencontext_core.backends.compression.terse import TerseCompressionBackend
from opencontext_core.backends.factory import BackendFactory
from opencontext_core.memory.agent import NullAgentMemoryStore


def test_factory_deep_degrades_to_compact():
    # deep is unavailable (llmlingua not installed) — should degrade to compact
    backend = BackendFactory.create_compression_backend("deep")
    assert isinstance(backend, CompactCompressionBackend)


def test_factory_compact():
    backend = BackendFactory.create_compression_backend("compact")
    assert isinstance(backend, CompactCompressionBackend)


def test_factory_terse():
    backend = BackendFactory.create_compression_backend("terse")
    assert isinstance(backend, TerseCompressionBackend)


def test_factory_none():
    backend = BackendFactory.create_compression_backend("none")
    assert isinstance(backend, NullCompressionBackend)


def test_factory_unknown_returns_terse():
    backend = BackendFactory.create_compression_backend("unknown_strategy_xyz")
    assert isinstance(backend, TerseCompressionBackend)


def test_factory_memory_disabled_returns_null():
    config = SimpleNamespace(memory=SimpleNamespace(enabled=False))
    with tempfile.TemporaryDirectory() as tmpdir:
        store = BackendFactory.create_memory_store(config, Path(tmpdir))
    assert isinstance(store, NullAgentMemoryStore)


def test_factory_memory_local_returns_local_memory_store():
    from opencontext_core.memory.graph import LocalMemoryStore

    config = SimpleNamespace(memory=SimpleNamespace(enabled=True, provider="local"))
    with tempfile.TemporaryDirectory() as tmpdir:
        store = BackendFactory.create_memory_store(config, Path(tmpdir))
    assert isinstance(store, LocalMemoryStore)
