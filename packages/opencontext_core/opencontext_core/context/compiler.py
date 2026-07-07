"""Converged evidence-plan compiler for all context-producing surfaces."""

from __future__ import annotations

import typing

from opencontext_core.context.packing import (
    ContextPackBuilder,
    _omission,
    _with_pack_metadata,
    build_pack_metrics,
    sanitize_context_pack,
)
from opencontext_core.models.context import ContextItem, ContextPackResult, ContextPriority
from opencontext_core.retrieval.contracts import EvidenceItem, EvidencePlan

if typing.TYPE_CHECKING:
    from opencontext_core.context.compression import CompressionEngine

#: Source types that represent symbol-level evidence (symbol-first retrieval).
_SYMBOL_SOURCE_TYPES = frozenset({"symbol", "graph_symbol"})


class ContextCompiler:
    """Pack, redact, and explain omissions for an already-ranked evidence plan.

    Ranking is owned by the planner's hybrid scorer; the compiler preserves that
    order (it used to re-rank with a weaker lexical ranker, discarding the hybrid
    graph/memory/freshness signals the planner had just computed).
    """

    def __init__(self) -> None:
        self._packer = ContextPackBuilder()

    def compile(
        self,
        plan: EvidencePlan,
        *,
        compression_engine: CompressionEngine | None = None,
        full_file_threshold: float | None = None,
    ) -> ContextPackResult:
        """Compile one planner output into a sanitized context pack.

        ``full_file_threshold`` wires ``retrieval.full_file_threshold`` ("relevance
        threshold below which a whole file is not loaded"): when the plan carries
        symbol evidence (symbol-first retrieval already surfaced the relevant
        spans), unprotected whole-file items scoring below the threshold are
        omitted with a traceable reason instead of filling leftover budget with
        low-relevance content. Without symbol evidence the threshold is inert —
        whole files are the only representation available.
        """

        ranked = [evidence_to_context_item(item) for item in plan.evidence]
        candidates = ranked
        threshold_omitted: list[ContextItem] = []
        has_symbol_evidence = any(item.source_type in _SYMBOL_SOURCE_TYPES for item in ranked)
        if full_file_threshold is not None and has_symbol_evidence:
            kept: list[ContextItem] = []
            for item in ranked:
                if (
                    item.source_type == "file"
                    and item.priority != ContextPriority.P0
                    and not item.metadata.get("protected")
                    and item.score < full_file_threshold
                ):
                    threshold_omitted.append(item)
                else:
                    kept.append(item)
            ranked = kept
        required_priorities = {ContextPriority.P0, ContextPriority.P1}
        packed = self._packer.pack(
            ranked,
            available_tokens=plan.request.max_tokens,
            required_priorities=required_priorities,
            compression_engine=compression_engine,
        )
        if threshold_omitted:
            omitted_items = [
                _with_pack_metadata(item, "below_full_file_threshold") for item in threshold_omitted
            ]
            packed = packed.model_copy(
                update={
                    "omitted": [*packed.omitted, *omitted_items],
                    "omissions": [
                        *packed.omissions,
                        *(_omission(item, "below_full_file_threshold") for item in omitted_items),
                    ],
                }
            )
        # Mandatory pack metrics block, computed against the pre-pack candidates
        # so input tokens and protected spans reflect what was actually considered.
        packed = packed.model_copy(update={"context": build_pack_metrics(packed, candidates)})
        return sanitize_context_pack(packed)


def evidence_to_context_item(item: EvidenceItem) -> ContextItem:
    """Convert planner evidence into packable context while preserving trace metadata."""

    priority = ContextPriority.P0 if item.protected else _priority_from_provenance(item)
    # Derive per-item retrieval_source from the planner's provenance dict so agents can
    # distinguish call_graph traversal items from query_match items (PR-AHE-006 task 6.4).
    retrieval_source = item.provenance.get("retrieval_source") or item.provenance.get(
        "source", "query_match"
    )
    metadata = {
        **item.provenance,
        "retrieval_source": retrieval_source,
        "evidence": {
            "id": item.id,
            "traceable_source": item.source,
            "confidence": item.confidence,
            "freshness": item.freshness.value,
            "request_surface": item.surface.value,
            "protected": item.protected,
        },
        "protected": item.protected,
    }
    return ContextItem(
        id=item.id,
        content=item.content,
        source=item.source,
        source_type=item.source_type,
        priority=priority,
        tokens=item.tokens,
        score=item.confidence,
        metadata=metadata,
        classification=item.classification,
        trusted=item.freshness.value == "current",
        source_trust=item.confidence,
    )


def _priority_from_provenance(item: EvidenceItem) -> ContextPriority:
    raw_priority = item.provenance.get("priority")
    if isinstance(raw_priority, str) and raw_priority in ContextPriority.__members__:
        return ContextPriority[raw_priority]
    return ContextPriority.P1
