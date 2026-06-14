"""BackendFactory — constructs backends from config with graceful degradation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.backends.compression.compact import CompactCompressionBackend
from opencontext_core.backends.compression.null import NullCompressionBackend
from opencontext_core.backends.compression.terse import TerseCompressionBackend
from opencontext_core.backends.protocols import CompressionBackend, VectorBackend
from opencontext_core.backends.vector.local import LocalVectorBackend
from opencontext_core.backends.vector.null import NullVectorBackend
from opencontext_core.exceptions import BackendUnavailableError


class BackendFactory:
    """
    Constructs backends from config. Graceful degradation: deep→compact, semantic→local.
    Callers never import backend classes directly — only via this factory.
    """

    @classmethod
    def create_compression_backend(cls, strategy: str) -> CompressionBackend:
        if strategy == "deep":
            try:
                from opencontext_core.backends.compression.deep import DeepCompressionBackend

                return DeepCompressionBackend()
            except BackendUnavailableError:
                return CompactCompressionBackend()
        elif strategy == "compact":
            return CompactCompressionBackend()
        elif strategy == "terse":
            return TerseCompressionBackend()
        elif strategy == "efficient":
            from opencontext_core.backends.compression.efficient import EfficientCompressionBackend
            return EfficientCompressionBackend()
        elif strategy == "none":
            return NullCompressionBackend()
        return TerseCompressionBackend()  # safe default

    @classmethod
    def create_vector_backend(cls, config: Any) -> VectorBackend:
        if not getattr(config, "semantic_search", False):
            return NullVectorBackend()
        try:
            from opencontext_core.backends.vector.semantic import SemanticVectorBackend

            host = getattr(config, "semantic_search_host", "localhost")
            port = getattr(config, "semantic_search_port", 6333)
            collection = getattr(config, "semantic_search_collection", "opencontext")
            return SemanticVectorBackend(host=host, port=port, collection=collection)
        except BackendUnavailableError:
            storage = Path(getattr(config, "storage_path", ".storage"))
            return LocalVectorBackend(storage)

    @classmethod
    def create_memory_store(cls, config: Any, storage_path: Path) -> Any:
        from opencontext_core.memory.agent import NullAgentMemoryStore

        memory_cfg = getattr(config, "memory", None)
        if memory_cfg is None or not getattr(memory_cfg, "enabled", True):
            return NullAgentMemoryStore()

        provider = getattr(memory_cfg, "provider", "local")
        if provider == "remote":
            try:
                from opencontext_core.memory.engram_store import EngramMemoryAdapter

                endpoint = getattr(memory_cfg, "endpoint", "http://localhost:4242")
                return EngramMemoryAdapter(endpoint)
            except Exception:
                pass

        from opencontext_core.memory.graph import LocalMemoryStore

        return LocalMemoryStore(storage_path / "memory.db")
