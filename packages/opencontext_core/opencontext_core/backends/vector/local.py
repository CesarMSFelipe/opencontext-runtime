"""Local vector backend — wraps file-based vector store."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class LocalVectorBackend:
    """Wraps the file-based vector store, adapting to the VectorBackend protocol."""

    def __init__(self, storage_path: Path | str = ".storage") -> None:
        from opencontext_core.embeddings.stores import LocalVectorStore

        self._storage_path = Path(storage_path)
        self._inner = LocalVectorStore(self._storage_path)
        # In-memory fallback for protocol-compliant store/search
        self._vectors: dict[str, list[float]] = {}
        self._meta: dict[str, dict[str, Any]] = {}

    def store(self, item_id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        self._vectors[item_id] = vector
        self._meta[item_id] = metadata

    def search(
        self, query_vector: list[float], top_k: int, filter: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        import math

        if not self._vectors:
            return []
        q_mag = math.sqrt(sum(v * v for v in query_vector))
        if q_mag == 0:
            return []
        query_norm = [v / q_mag for v in query_vector]

        scores: list[tuple[float, str]] = []
        for item_id, vector in self._vectors.items():
            meta = self._meta.get(item_id, {})
            if filter:
                if not all(meta.get(k) == v for k, v in filter.items()):
                    continue
            v_mag = math.sqrt(sum(v * v for v in vector))
            if v_mag == 0:
                continue
            vec_norm = [v / v_mag for v in vector]
            dot = sum(q * v for q, v in zip(query_norm, vec_norm, strict=False))
            scores.append((dot, item_id))

        scores.sort(reverse=True)
        return [
            {"item_id": iid, "score": sc, **self._meta.get(iid, {})} for sc, iid in scores[:top_k]
        ]

    def delete(self, item_id: str) -> None:
        self._vectors.pop(item_id, None)
        self._meta.pop(item_id, None)

    def clear(self) -> None:
        self._vectors.clear()
        self._meta.clear()
