"""Null vector backend — no-op, safe default."""

from __future__ import annotations

from typing import Any


class NullVectorBackend:
    def store(self, item_id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        return

    def search(
        self, query_vector: list[float], top_k: int, filter: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        return []

    def delete(self, item_id: str) -> None:
        return

    def clear(self) -> None:
        return
