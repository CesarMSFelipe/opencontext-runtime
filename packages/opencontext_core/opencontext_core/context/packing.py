"""Token-aware context packing."""

from __future__ import annotations

import typing

from opencontext_core.context.ranking import SOURCE_TRUST
from opencontext_core.models.context import (
    CompressionPackMetadata,
    ContextItem,
    ContextOmission,
    ContextPackMetrics,
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
            # as-is. Try to COMPRESS it to fit before omitting — otherwise a
            # single over-budget span yields ZERO content instead of a compressed
            # version (the packer would drop a 2,360-token function under a
            # 500-token budget rather than compress it). Engine-gated: with no
            # compression engine the behaviour is unchanged (omit).
            if item.tokens > available_tokens:
                remaining = available_tokens - used_tokens
                if compression_engine and remaining > 10:
                    original_tokens = item.tokens
                    candidate = compression_engine.compress_item(item).item
                    if used_tokens + candidate.tokens <= available_tokens:
                        included.append(
                            _with_pack_metadata(candidate, "included_with_dynamic_compression")
                        )
                        used_tokens += candidate.tokens
                        compression_tokens_before += original_tokens
                        compression_tokens_after += candidate.tokens
                        compression_items_count += 1
                        continue
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
    # Short human-readable reason so every pack item explains its selection.
    if not metadata.get("reason"):
        retrieval_source = metadata.get("retrieval_source") or item.source_type
        metadata["reason"] = f"{decision} via {retrieval_source}"
    return item.model_copy(update={"metadata": metadata})


def _omission(item: ContextItem, reason: str) -> ContextOmission:
    return ContextOmission(
        item_id=item.id,
        reason=reason,
        tokens=item.tokens,
        score=item.score,
    )


_KG_RETRIEVAL_SOURCES = {"graph", "graph_expansion", "call_graph"}
_KG_ID_PREFIXES = ("graph:", "fts:")


def _is_kg_item(item: ContextItem) -> bool:
    retrieval_source = str(item.metadata.get("retrieval_source", ""))
    return retrieval_source in _KG_RETRIEVAL_SOURCES or item.id.startswith(_KG_ID_PREFIXES)


def _is_memory_item(item: ContextItem) -> bool:
    return item.source_type == "memory" or item.metadata.get("retrieval_source") == "memory"


def _kg_edges_for(item: ContextItem) -> int:
    """Edges justifying this item: provenance relationships, or one expansion hop."""
    provenance = item.metadata.get("graph_provenance")
    if isinstance(provenance, dict):
        relationships = provenance.get("relationships")
        if isinstance(relationships, list) and relationships:
            return len(relationships)
    if item.metadata.get("retrieval_source") == "graph_expansion":
        return 1
    return 0


def build_pack_metrics(
    result: ContextPackResult,
    candidates: list[ContextItem] | None = None,
) -> ContextPackMetrics:
    """Build the mandatory pack metrics block from a packed result.

    ``candidates`` is the full pre-pack candidate set (used for the input-token
    estimate and pre-compression protected-span detection); when omitted, the
    packed items themselves are used as the best available approximation.
    """

    from opencontext_core.context.protection import ProtectedSpanManager

    originals = candidates if candidates is not None else [*result.included, *result.omitted]
    input_tokens = sum(item.tokens for item in originals)

    compression_ratio: float | None = None
    if result.compression is not None and result.compression.tokens_before > 0:
        compression_ratio = round(
            result.compression.tokens_after / result.compression.tokens_before, 4
        )
        # Compression shrank candidate tokens in place; restore the pre-compression sum.
        if candidates is None:
            input_tokens += result.compression.tokens_before - result.compression.tokens_after

    kg_nodes = sum(1 for item in result.included if _is_kg_item(item))
    kg_edges = sum(_kg_edges_for(item) for item in result.included)
    memory_hits = sum(1 for item in result.included if _is_memory_item(item))

    detector = ProtectedSpanManager()
    original_by_id = {item.id: item for item in originals}
    protected_spans = 0
    protected_spans_kept = 0
    for item in result.included:
        original = original_by_id.get(item.id, item)
        detected = len(detector.detect(original.content))
        if item.content == original.content:
            kept = detected
        else:
            kept = len(detector.detect(item.content))
        protected_spans += detected
        protected_spans_kept += min(kept, detected)

    return ContextPackMetrics(
        budget_tokens=result.available_tokens,
        input_tokens_estimated=input_tokens,
        output_tokens_estimated=result.used_tokens,
        compression_ratio=compression_ratio,
        kg_used=kg_nodes > 0,
        kg_nodes_used=kg_nodes,
        kg_edges_used=kg_edges,
        memory_hits=memory_hits,
        protected_spans=protected_spans,
        protected_spans_kept=protected_spans_kept,
        excluded_files=len(result.omissions),
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
