"""Converged evidence-plan compiler for all context-producing surfaces."""

from __future__ import annotations

import typing

from opencontext_core.config import RankingWeightsConfig
from opencontext_core.context.packing import ContextPackBuilder, sanitize_context_pack
from opencontext_core.context.ranking import ContextRanker
from opencontext_core.models.context import ContextItem, ContextPackResult, ContextPriority
from opencontext_core.retrieval.contracts import EvidenceItem, EvidencePlan

if typing.TYPE_CHECKING:
    from opencontext_core.context.compression import CompressionEngine


class ContextCompiler:
    """Rank, pack, redact, and explain omissions for an evidence plan."""

    def __init__(self, *, ranking_weights: RankingWeightsConfig) -> None:
        self._ranker = ContextRanker(ranking_weights)
        self._packer = ContextPackBuilder()

    def compile(
        self,
        plan: EvidencePlan,
        *,
        compression_engine: CompressionEngine | None = None,
    ) -> ContextPackResult:
        """Compile one planner output into a sanitized context pack."""

        ranked = self._ranker.rank([evidence_to_context_item(item) for item in plan.evidence])
        required_priorities = {ContextPriority.P0, ContextPriority.P1}
        packed = self._packer.pack(
            ranked,
            available_tokens=plan.request.max_tokens,
            required_priorities=required_priorities,
            compression_engine=compression_engine,
        )
        return sanitize_context_pack(packed)


def evidence_to_context_item(item: EvidenceItem) -> ContextItem:
    """Convert planner evidence into packable context while preserving trace metadata."""

    priority = ContextPriority.P0 if item.protected else _priority_from_provenance(item)
    metadata = {
        **item.provenance,
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
