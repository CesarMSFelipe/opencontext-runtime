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
    def create_memory_store(
        cls, config: Any, storage_path: Path, *, engram_client: Any = None
    ) -> Any:
        """Resolve exactly one AgentMemoryStore from ``memory.provider``.

        ``auto``   -> couple to a co-resident Engram if one is detected, else
        local; ``engram`` -> couple to Engram (injected client or a detected
        co-resident install); any other provider -> ``LocalMemoryStore``;
        disabled -> ``Null``.

        Coupling means ``CompositeMemoryStore``: Engram owns EPISODIC/SEMANTIC,
        the local store owns PROCEDURAL/FAILURE/WORKING.

        Degrades gracefully (never raises): if no Engram client can be resolved
        or constructing it fails, falls back to ``LocalMemoryStore``. In
        ``AIR_GAPPED`` security mode no engram/MCP call may be issued, so Engram
        coupling is force-degraded to the local store (whose methods never touch
        an external client).
        """
        from opencontext_core.memory.agent import NullAgentMemoryStore
        from opencontext_core.memory.graph import LocalMemoryStore

        memory_cfg = getattr(config, "memory", None)
        if memory_cfg is None or not getattr(memory_cfg, "enabled", True):
            return NullAgentMemoryStore()

        def _local() -> Any:
            return LocalMemoryStore(storage_path / "memory.db")

        provider = getattr(memory_cfg, "provider", "auto")
        if provider in ("engram", "auto"):
            if cls._is_air_gapped(config):
                # Air-gapped: never issue an engram/MCP call — use local only.
                return _local()
            client = cls._resolve_engram_client(engram_client)
            project = "default"
            if client is None:
                # No injected client — couple to a detected co-resident Engram.
                from opencontext_core.memory.engram_bridge import (
                    default_engram_client,
                    engram_project,
                )

                client = default_engram_client()
                if client is not None:
                    project = engram_project()
            if client is None:
                # Engram absent -> our full multi-level local memory.
                return _local()
            try:
                from opencontext_core.memory.composite import CompositeMemoryStore
                from opencontext_core.memory.engram_mcp_store import EngramMemoryStore

                return CompositeMemoryStore(
                    local=_local(),
                    engram=EngramMemoryStore(client, project=project),
                )
            except Exception:
                return _local()

        return _local()

    @staticmethod
    def _is_air_gapped(config: Any) -> bool:
        security = getattr(config, "security", None)
        mode = getattr(security, "mode", None)
        return str(getattr(mode, "value", mode)) == "air_gapped"

    @staticmethod
    def _resolve_engram_client(engram_client: Any) -> Any:
        """Resolve the injected engram client, never raising.

        Accepts either a ready client instance or a zero-arg factory callable.
        Returns ``None`` (caller degrades) when unavailable or construction
        fails.
        """
        if engram_client is None:
            return None
        if callable(engram_client) and not (
            hasattr(engram_client, "mem_search") or hasattr(engram_client, "mem_save")
        ):
            try:
                return engram_client()
            except Exception:
                return None
        return engram_client
