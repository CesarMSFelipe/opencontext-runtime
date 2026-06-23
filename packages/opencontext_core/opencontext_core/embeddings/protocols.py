"""Protocols and interfaces for embedding and vector storage."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from opencontext_core.embeddings.models import (
    EmbeddedItem,
    EmbeddingBatch,
    EmbeddingStats,
    VectorSearchResult,
)


class VectorStore(Protocol):
    """Storage interface for vector embeddings."""

    def store(self, items: list[EmbeddedItem]) -> None:
        """Store completed embeddings with their vectors."""
        ...

    def store_batch(self, batch: EmbeddingBatch) -> None:
        """Store a batch of embeddings."""
        ...

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        """Perform vector similarity search."""
        ...

    def get(self, item_id: str) -> EmbeddedItem | None:
        """Retrieve a specific embedding by ID."""
        ...

    def delete(self, item_id: str) -> None:
        """Delete an embedding."""
        ...

    def clear_project(self, project_name: str) -> None:
        """Clear all embeddings for a project."""
        ...

    def prune_absent_sources(self, keep_paths: Iterable[str], project_name: str) -> int:
        """Drop a project's vectors whose ``source_path`` is not in ``keep_paths``."""
        ...

    def stats(self) -> EmbeddingStats:
        """Get storage statistics."""
        ...


class EmbeddingGenerator(Protocol):
    """Interface for generating embeddings from text."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        ...

    def dimensions(self) -> int:
        """Return the vector dimensions for this generator."""
        ...

    def model_name(self) -> str:
        """Return the model identifier."""
        ...


class EmbeddingWorker(Protocol):
    """Background worker for asynchronous embedding generation."""

    async def start(self) -> None:
        """Start the background worker."""
        ...

    async def stop(self) -> None:
        """Stop the background worker gracefully."""
        ...

    async def queue_items(self, items: list[EmbeddedItem]) -> None:
        """Queue items for embedding generation."""
        ...

    def stats(self) -> EmbeddingStats:
        """Get worker statistics."""
        ...

    async def health(self) -> bool:
        """Check if the worker is healthy and processing."""
        ...
