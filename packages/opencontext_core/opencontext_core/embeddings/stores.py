"""Vector storage backends for embeddings."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from opencontext_core.embeddings.models import (
    EmbeddedItem,
    EmbeddingBatch,
    EmbeddingStats,
    VectorSearchResult,
)
from opencontext_core.embeddings.protocols import VectorStore


class LocalVectorStore(VectorStore):
    """File-based vector store using JSONL storage.

    Stores embeddings as JSONL lines in .storage/opencontext/embeddings/
    Maintains an in-memory index for search. Suitable for development
    and small-scale deployments (< 10k vectors).
    """

    def __init__(self, base_path: Path | str = ".storage/opencontext") -> None:
        self.base_path = Path(base_path)
        self.embeddings_dir = self.base_path / "embeddings"
        self.index_path = self.embeddings_dir / "index.jsonl"
        self._vectors: dict[str, list[float]] = {}  # item_id -> vector
        self._metadata: dict[str, EmbeddedItem] = {}  # item_id -> EmbeddedItem
        self._dirty: set[str] = set()  # Pending items not yet persisted
        self._load()

    def _load(self) -> None:
        """Load all embeddings from disk into memory."""
        self.embeddings_dir.mkdir(parents=True, exist_ok=True)
        self._vectors.clear()
        self._metadata.clear()

        if not self.index_path.exists():
            return

        with self.index_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    item_id = data.get("id")
                    vector = data.get("vector")
                    if item_id and vector:
                        self._vectors[item_id] = vector
                        # Reconstruct EmbeddedItem for metadata
                        self._metadata[item_id] = EmbeddedItem.model_validate(data)
                except Exception:
                    continue  # Skip malformed lines

    def _persist_batch(self, items: list[EmbeddedItem]) -> None:
        """Append a batch of embeddings to disk."""
        self.embeddings_dir.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8") as f:
            for item in items:
                if item.vector is not None:
                    f.write(item.model_dump_json() + "\n")
                # Mark as not dirty regardless - we've persisted this representation
                self._dirty.discard(item.id)

    def store(self, items: list[EmbeddedItem]) -> None:
        """Store completed embeddings with their vectors."""
        persisted_items: list[EmbeddedItem] = []
        for item in items:
            vector = item.vector
            if vector is None:
                continue
            self._vectors[item.id] = vector
            self._metadata[item.id] = item
            self._dirty.add(item.id)
            persisted_items.append(item)

        if persisted_items:
            self._persist_batch(persisted_items)

    def store_batch(self, batch: EmbeddingBatch) -> None:
        """Store a batch of embeddings."""
        self.store(batch.items)

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        """Perform vector similarity search using cosine similarity."""
        if not self._vectors:
            return []

        # Normalize query vector
        q_mag = math.sqrt(sum(v * v for v in query_vector))
        if q_mag == 0:
            return []
        query_norm = [v / q_mag for v in query_vector]

        scores = []
        for item_id, vector in self._vectors.items():
            metadata = self._metadata.get(item_id)
            if metadata is None:
                continue

            # Apply filters if provided
            if filters:
                match = True
                for key, value in filters.items():
                    if metadata.metadata.get(key) != value:
                        match = False
                        break
                if not match:
                    continue

            # Compute cosine similarity
            v_mag = math.sqrt(sum(v * v for v in vector))
            if v_mag == 0:
                continue
            vector_norm = [v / v_mag for v in vector]

            dot = sum(q * v for q, v in zip(query_norm, vector_norm, strict=False))
            scores.append((item_id, dot, metadata))

        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for _item_id, score, metadata in scores[:top_k]:
            results.append(
                VectorSearchResult(
                    item_id=metadata.item_id,
                    score=score,
                    content=metadata.content,
                    source_type=metadata.item_type,
                    source_path=metadata.metadata.get("source_path", ""),
                    metadata=metadata.metadata,
                )
            )
        return results

    def get(self, item_id: str) -> EmbeddedItem | None:
        """Retrieve a specific embedding record."""
        return self._metadata.get(item_id)

    def delete(self, item_id: str) -> None:
        """Delete an embedding (mark for cleanup on rebuild)."""
        self._vectors.pop(item_id, None)
        self._metadata.pop(item_id, None)
        self._dirty.discard(item_id)
        # Note: Actual file line removal requires rebuild; for v0.1 we leave it

    def clear_project(self, project_name: str) -> None:
        """Clear all embeddings for a project."""
        to_remove = [
            item_id for item_id, meta in self._metadata.items() if meta.project_name == project_name
        ]
        for item_id in to_remove:
            self._vectors.pop(item_id, None)
            self._metadata.pop(item_id, None)
        # For v0.1, we don't rewrite the file; real cleanup would need rebuild

    def stats(self) -> EmbeddingStats:
        """Get storage statistics."""
        from datetime import datetime

        last_file_mtime = None
        if self.index_path.exists():
            try:
                last_file_mtime = datetime.fromtimestamp(self.index_path.stat().st_mtime)
            except Exception:
                pass

        return EmbeddingStats(
            total_items=len(self._metadata),
            embedded_count=len([m for m in self._metadata.values() if m.embedded_at is not None]),
            pending_count=len(self._dirty),
            failed_count=0,  # Not tracked in v0.1
            average_latency_ms=0.0,  # Would need timing data
            queue_depth=len(self._dirty),
            last_activity=last_file_mtime,
        )


class NullVectorStore(VectorStore):
    """No-op vector store for testing or when embeddings are disabled."""

    def store(self, items: list[EmbeddedItem]) -> None:
        pass

    def store_batch(self, batch: EmbeddingBatch) -> None:
        pass

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        return []

    def get(self, item_id: str) -> EmbeddedItem | None:
        return None

    def delete(self, item_id: str) -> None:
        pass

    def clear_project(self, project_name: str) -> None:
        pass

    def stats(self) -> EmbeddingStats:
        return EmbeddingStats(
            total_items=0,
            embedded_count=0,
            pending_count=0,
            failed_count=0,
            average_latency_ms=0.0,
            queue_depth=0,
            last_activity=None,
        )
