"""Backend protocols for compression and vector search."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from opencontext_core.models.context import ProtectedSpan


@runtime_checkable
class CompressionBackend(Protocol):
    """ISP: single compress() method. All backends must preserve protected_spans verbatim."""

    name: str

    def compress(self, text: str, protected_spans: list[ProtectedSpan]) -> str: ...


@runtime_checkable
class VectorBackend(Protocol):
    """ISP: minimal interface for vector search."""

    def store(self, item_id: str, vector: list[float], metadata: dict[str, Any]) -> None: ...

    def search(
        self, query_vector: list[float], top_k: int, filter: dict[str, Any] | None
    ) -> list[dict[str, Any]]: ...

    def delete(self, item_id: str) -> None: ...

    def clear(self) -> None: ...
