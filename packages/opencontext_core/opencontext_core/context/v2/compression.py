from __future__ import annotations

"""Context v2 compression — token-budget trim with omission tracking."""

from typing import Any

from opencontext_core.context.v2.envelope import ContextEnvelope


class ContextCompressor:
    """Trims envelope.items down to a token budget; records omissions."""

    def compress(
        self, envelope: ContextEnvelope, target_tokens: int | None = None
    ) -> ContextEnvelope:
        target = target_tokens if target_tokens is not None else envelope.budget
        trimmed: list[dict[Any, Any]] = []
        used = 0
        for item in envelope.items:
            tokens = len(item.get("content", "")) // 4  # NOTE: rough 4-chars/token
            if used + tokens > target:
                envelope.omissions.append(f"omitted {item.get('id', '?')} for budget")
                continue
            trimmed.append(item)
            used += tokens
        envelope.items = trimmed
        envelope.tokens_used = used
        envelope.compressed = True
        return envelope


__all__ = ["ContextCompressor"]
