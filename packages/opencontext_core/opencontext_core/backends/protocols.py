"""Backend protocols for compression and vector search."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from opencontext_core.models.context import ProtectedSpan


@runtime_checkable
class CompressionBackend(Protocol):
    """ISP: single compress() method. All backends must preserve protected_spans verbatim."""

    name: str

    def compress(self, text: str, protected_spans: list[ProtectedSpan]) -> str: ...
