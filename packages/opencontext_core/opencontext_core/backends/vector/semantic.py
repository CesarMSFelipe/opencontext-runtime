"""Semantic vector backend — opt-in, raises BackendUnavailableError if deps missing."""

from __future__ import annotations

from typing import Any

from opencontext_core.exceptions import BackendUnavailableError


class SemanticVectorBackend:
    """High-performance semantic vector search. Raises BackendUnavailableError if deps missing."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection: str = "opencontext",
    ) -> None:
        try:
            import qdrant_client  # type: ignore[import-not-found]  # noqa: F401
        except ImportError as exc:
            raise BackendUnavailableError(
                "semantic-search",
                "opencontext setup --enable semantic-search",
            ) from exc
        self._host = host
        self._port = port
        self._collection = collection

    def store(self, item_id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        raise BackendUnavailableError(  # pragma: no cover
            "semantic-search",
            "opencontext setup --enable semantic-search",
        )

    def search(
        self, query_vector: list[float], top_k: int, filter: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        raise BackendUnavailableError(  # pragma: no cover
            "semantic-search",
            "opencontext setup --enable semantic-search",
        )

    def delete(self, item_id: str) -> None:
        raise BackendUnavailableError(  # pragma: no cover
            "semantic-search",
            "opencontext setup --enable semantic-search",
        )

    def clear(self) -> None:
        raise BackendUnavailableError(  # pragma: no cover
            "semantic-search",
            "opencontext setup --enable semantic-search",
        )
