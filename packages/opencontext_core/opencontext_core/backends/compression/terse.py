"""Terse compression backend — wraps TerseCompressor."""

from __future__ import annotations

from opencontext_core.compression.terse import TerseCompressor
from opencontext_core.models.context import ProtectedSpan


class TerseCompressionBackend:
    """Wraps TerseCompressor, preserving protected spans verbatim."""

    name = "terse"

    def __init__(self) -> None:
        self._inner = TerseCompressor()

    def compress(self, text: str, protected_spans: list[ProtectedSpan]) -> str:
        """Compress text; protected span content is always verbatim in output."""
        if not text:
            return text
        if not protected_spans:
            return self._inner.compress(text)

        # Build sorted list of protected regions
        spans = sorted(protected_spans, key=lambda s: s.start)

        parts: list[str] = []
        pos = 0
        for span in spans:
            start = max(span.start, pos)
            end = span.end
            if start > pos:
                prose = text[pos:start]
                parts.append(self._inner.compress(prose))
            parts.append(text[start:end])
            pos = end
        if pos < len(text):
            parts.append(self._inner.compress(text[pos:]))

        return "".join(parts)
