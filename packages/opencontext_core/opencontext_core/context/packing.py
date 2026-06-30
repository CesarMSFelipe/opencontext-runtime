"""Token-aware context packing."""

from __future__ import annotations

import typing

from opencontext_core.context.ranking import SOURCE_TRUST
from opencontext_core.models.context import (
    CompressionPackMetadata,
    ContextItem,
    ContextOmission,
    ContextPackResult,
    ContextPriority,
)
from opencontext_core.safety.redaction import SinkGuard

if typing.TYPE_CHECKING:
    from opencontext_core.context.compression import CompressionEngine


# DEPRECATED(2.0): legacy context packing; superseded by the PR-010 ContextEngine. Still the
# live default; remove when runtime.context_engine_enabled is default + legacy removed
# (milestone-D).
class ContextPackBuilder:
    """Packs ranked context under a hard token budget with traceable decisions."""

    def pack(
        self,
        items: list[ContextItem],
        available_tokens: int,
        required_priorities: set[ContextPriority] | None = None,
        compression_engine: CompressionEngine | None = None,
    ) -> ContextPackResult:
        """Pack context under budget using priority and value density."""

        required = required_priorities or {ContextPriority.P0, ContextPriority.P1}
        ordered_items = sorted(items, key=self._sort_key)
        included: list[ContextItem] = []
        omitted: list[ContextItem] = []
        omissions: list[ContextOmission] = []
        used_tokens = 0
        # Track compression activity to emit truthful pack-level metadata.
        compression_tokens_before = 0
        compression_tokens_after = 0
        compression_items_count = 0
        for item in ordered_items:
            # If item itself exceeds total available budget, it can never fit
            if item.tokens > available_tokens:
                omitted_item = _with_pack_metadata(item, "item_exceeds_available_budget")
                omitted.append(omitted_item)
                omissions.append(_omission(omitted_item, "item_exceeds_available_budget"))
                continue

            # Check if it fits as-is
            if used_tokens + item.tokens <= available_tokens:
                included.append(_with_pack_metadata(item, "included"))
                used_tokens += item.tokens
                continue

            # If it doesn't fit, try dynamic compression if an engine is provided.
            # Applies to ANY priority, not just P0/P1: compressing a large item to
            # fit is strictly better than omitting it, and it is the only reason
            # the compression engine fires on a typical (mostly-fitting) pack.
            if compression_engine:
                # Attempt compression to fit remaining budget
                remaining = available_tokens - used_tokens
                if remaining > 10:  # Only bother if there's meaningful space
                    original_tokens = item.tokens
                    compressed_result = compression_engine.compress_item(item)
                    candidate = compressed_result.item
                    if used_tokens + candidate.tokens <= available_tokens:
                        included.append(
                            _with_pack_metadata(candidate, "included_with_dynamic_compression")
                        )
                        used_tokens += candidate.tokens
                        # Record that compression actually ran and reduced tokens.
                        compression_tokens_before += original_tokens
                        compression_tokens_after += candidate.tokens
                        compression_items_count += 1
                        continue

            # Still doesn't fit
            reason = (
                "required_priority_budget_exhausted"
                if item.priority in required
                else "token_budget_exceeded"
            )
            omitted_item = _with_pack_metadata(item, reason)
            omitted.append(omitted_item)
            omissions.append(_omission(omitted_item, reason))

        # Only emit compression metadata when compression actually ran.
        pack_compression: CompressionPackMetadata | None = None
        if compression_items_count > 0:
            pack_compression = CompressionPackMetadata(
                enabled=True,
                tokens_before=compression_tokens_before,
                tokens_after=compression_tokens_after,
                items_compressed=compression_items_count,
            )

        return ContextPackResult(
            included=included,
            omitted=omitted,
            used_tokens=used_tokens,
            available_tokens=available_tokens,
            omissions=omissions,
            compression=pack_compression,
        )

    def _sort_key(self, item: ContextItem) -> tuple[int, float, float, float, str]:
        source_trust = SOURCE_TRUST.get(item.source_type, 0.5)
        value_density = item.score / max(item.tokens, 1)
        return (
            int(item.priority),
            -item.score,
            -value_density,
            -source_trust,
            item.id,
        )


def _with_pack_metadata(item: ContextItem, decision: str) -> ContextItem:
    metadata = dict(item.metadata)
    metadata["context_pack"] = {
        "decision": decision,
        "value_per_token": item.score / max(item.tokens, 1),
        "source_trust": SOURCE_TRUST.get(item.source_type, 0.5),
    }
    return item.model_copy(update={"metadata": metadata})


def _omission(item: ContextItem, reason: str) -> ContextOmission:
    return ContextOmission(
        item_id=item.id,
        reason=reason,
        tokens=item.tokens,
        score=item.score,
    )


def sanitize_context_pack(result: ContextPackResult) -> ContextPackResult:
    """Redact pack content before CLI/API/export sinks."""

    guard = SinkGuard()
    return result.model_copy(
        update={
            "included": [_sanitize_item(guard, item) for item in result.included],
            "omitted": [_sanitize_item(guard, item) for item in result.omitted],
        }
    )


def _sanitize_item(guard: SinkGuard, item: ContextItem) -> ContextItem:
    content, redacted = guard.redact(item.content)
    metadata = dict(item.metadata)
    metadata["redacted"] = redacted or bool(metadata.get("redacted", False))
    return item.model_copy(
        update={
            "content": content,
            "metadata": metadata,
            "redacted": redacted or item.redacted,
        }
    )
