"""Null compression backend — pass-through."""

from __future__ import annotations

from opencontext_core.models.context import ProtectedSpan


class NullCompressionBackend:
    name = "null"

    def compress(self, text: str, protected_spans: list[ProtectedSpan]) -> str:
        return text
