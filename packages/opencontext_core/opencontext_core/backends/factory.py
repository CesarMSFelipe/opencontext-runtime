"""BackendFactory — constructs backends from config with graceful degradation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.backends.compression.compact import CompactCompressionBackend
from opencontext_core.backends.compression.null import NullCompressionBackend
from opencontext_core.backends.compression.terse import TerseCompressionBackend
from opencontext_core.backends.protocols import CompressionBackend
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
            embedder, vector_store = cls._memory_semantic_backends(config, storage_path)
            return LocalMemoryStore(
                storage_path / "memory.db",
                vector_store=vector_store,
                embedder=embedder,
            )

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
    def _memory_semantic_backends(config: Any, storage_path: Path) -> tuple[Any, Any]:
        """Return (embedder, vector_store) for semantic memory recall when embeddings
        are enabled, else (None, None).

        Without these the LocalMemoryStore semantic leg is dead code. Vectors live
        under ``storage_path/memory`` so they never collide with the code index.
        Never raises — degrades to lexical recall on any error.
        """
        emb_cfg = getattr(config, "embedding", None)
        if emb_cfg is None or not getattr(emb_cfg, "enabled", False):
            return None, None
        try:
            from opencontext_core.embeddings.generators import create_generator
            from opencontext_core.embeddings.stores import LocalVectorStore

            return create_generator(config), LocalVectorStore(storage_path / "memory")
        except Exception:
            return None, None

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
