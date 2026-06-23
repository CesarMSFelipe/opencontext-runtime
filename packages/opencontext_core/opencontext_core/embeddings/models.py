"""Data models for embeddings and vector storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.models.context import DataClassification


class EmbeddedItem(BaseModel):
    """An item that has been or needs to be, embedded."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique identifier for this embedding record.")
    item_id: str = Field(description="ID of the source context item.")
    item_type: str = Field(description="Type of source: 'symbol', 'file', 'fact', 'decision'.")
    project_name: str = Field(description="Project this item belongs to.")
    content: str = Field(description="Text content that was embedded.")
    vector: list[float] | None = Field(
        default=None, description="Embedding vector if already generated."
    )
    embedding_model: str | None = Field(
        default=None, description="Model used to generate embedding."
    )
    dimensions: int | None = Field(default=None, description="Vector dimensions.")
    classification: DataClassification = Field(
        description="Data classification for access control."
    )
    created_at: datetime = Field(description="When this embedding record was created.")
    embedded_at: datetime | None = Field(default=None, description="When the vector was generated.")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional embedding metadata."
    )

    @classmethod
    def create(
        cls,
        item_id: str,
        item_type: str,
        project_name: str,
        content: str,
        classification: DataClassification = DataClassification.INTERNAL,
        metadata: dict[str, Any] | None = None,
    ) -> EmbeddedItem:
        """Create a new embedding record."""
        return cls(
            # Deterministic id (one record per source item): re-indexing the same
            # file/symbol reuses this id so the store overwrites in place instead of
            # accumulating a fresh copy each pass. A timestamp here defeated dedup and
            # grew index.jsonl unbounded; created_at below records the time instead.
            id=f"emb_{item_id}",
            item_id=item_id,
            item_type=item_type,
            project_name=project_name,
            content=content,
            classification=classification,
            created_at=datetime.now(tz=UTC),
            metadata=metadata or {},
        )


class VectorSearchResult(BaseModel):
    """Result from a vector similarity search."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(description="ID of the matched item.")
    score: float = Field(description="Similarity score (0-1).")
    content: str = Field(description="Matched content.")
    source_type: str = Field(description="Type of source.")
    source_path: str = Field(description="Path or location of source.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional item metadata.")


class EmbeddingBatch(BaseModel):
    """Batch of items to embed together."""

    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(description="Unique batch identifier.")
    items: list[EmbeddedItem] = Field(description="Items in this batch.")
    created_at: datetime = Field(description="Batch creation timestamp.")
    status: str = Field(description="Batch status: 'pending', 'processing', 'done', 'failed'.")
    error: str | None = Field(default=None, description="Error message if failed.")

    @classmethod
    def create(cls, items: list[EmbeddedItem]) -> EmbeddingBatch:
        """Create a new batch from items."""
        return cls(
            batch_id=f"batch_{datetime.now(tz=UTC).timestamp()}_{len(items)}",
            items=items,
            created_at=datetime.now(tz=UTC),
            status="pending",
        )


class EmbeddingStats(BaseModel):
    """Statistics about embedding operations."""

    model_config = ConfigDict(extra="forbid")

    total_items: int = Field(ge=0, description="Total items requiring embeddings.")
    embedded_count: int = Field(ge=0, description="Number of items successfully embedded.")
    pending_count: int = Field(ge=0, description="Items pending embedding.")
    failed_count: int = Field(ge=0, description="Items that failed embedding.")
    average_latency_ms: float = Field(description="Average embedding generation latency.")
    queue_depth: int = Field(ge=0, description="Current queue depth.")
    last_activity: datetime | None = Field(
        default=None, description="Last embedding activity timestamp."
    )
