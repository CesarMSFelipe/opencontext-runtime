"""Context v2 engine — single ``ContextEngine.build()`` entry point.

The engine composes the four context layers (route → rank → score → compress)
and emits a ``ContextEnvelope`` + ``ContextReceipt`` pair. The receipt's
``envelope_hash`` is a deterministic SHA-256 over a canonicalised view of the
envelope; the same items + budget always produce the same hash.

Amendment A5 (commit-019): the engine emits a ``FullFileReadJustification``
for every input item whose ``retrieval_strategy == "FULL_FILE"``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from opencontext_core.context.v2.budget import ResourceBudget
from opencontext_core.context.v2.compression import ContextCompressor
from opencontext_core.context.v2.envelope import ContextEnvelope
from opencontext_core.context.v2.ranking.score import usefulness
from opencontext_core.context.v2.receipt import (
    ContextReceipt,
    EvidenceRef,
    FullFileReadJustification,
)
from opencontext_core.context.v2.routing import ContextRouter


@dataclass
class ContextBuildResult:
    envelope: ContextEnvelope
    receipt: ContextReceipt


def _envelope_hash(envelope: ContextEnvelope) -> str:
    canonical = json.dumps(
        {
            "task": envelope.task,
            "items": envelope.items,
            "tokens_used": envelope.tokens_used,
            "budget": envelope.budget,
            "omissions": sorted(envelope.omissions),
        },
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _ranking_hash(items: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        [{"id": it.get("id"), "content": it.get("content", "")} for it in items],
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _budget_hash(budget: int) -> str:
    return hashlib.sha256(f"budget={budget}".encode()).hexdigest()


def _confidence(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    total = sum(
        usefulness(
            relevance=float(it.get("relevance", 0.0)),
            freshness=float(it.get("recency", 0.0)),
            confidence=float(it.get("confidence", 0.0)),
        )
        for it in items
    )
    return round(min(1.0, total / max(1, len(items))), 6)


class ContextEngine:
    """Compose routing → ranking → usefulness scoring → compression."""

    def __init__(
        self,
        router: ContextRouter | None = None,
        compressor: ContextCompressor | None = None,
    ) -> None:
        self._router = router or ContextRouter()
        self._compressor = compressor or ContextCompressor()

    def build(
        self,
        *,
        task: str,
        items: list[dict[str, Any]],
        request_id: str,
        workflow: str,
        node: str,
        budget: int,
    ) -> ContextBuildResult:
        envelope = ContextEnvelope(task=task, items=list(items), budget=budget)
        envelope = self._router.route(envelope)
        # L4 usefulness ranking — recompute score, sort descending.
        envelope.items = sorted(
            envelope.items,
            key=lambda it: usefulness(
                relevance=float(it.get("relevance", 0.0)),
                freshness=float(it.get("recency", 0.0)),
                confidence=float(it.get("confidence", 0.0)),
            ),
            reverse=True,
        )
        envelope = self._compressor.compress(envelope)
        # If compression marked omissions but the actual items got culled, keep the
        # envelope's omission list consistent with the surviving items.
        included_ids = {it.get("id") for it in envelope.items}
        omitted_refs = [
            EvidenceRef(kind="file", id=str(it.get("id")), tokens=int(it.get("tokens", 0)))
            for it in items
            if it.get("id") not in included_ids
        ]
        included_refs = [
            EvidenceRef(kind="file", id=str(it.get("id")), tokens=int(it.get("tokens", 0)))
            for it in envelope.items
        ]
        # A5: emit a FullFileReadJustification per input item whose
        # ``retrieval_strategy`` is FULL_FILE (the engine asked to load the
        # whole file rather than a snippet/symbol view).
        full_file_reads = [
            FullFileReadJustification(
                path=str(it.get("path", it.get("id", ""))),
                reason=str(it.get("reason", "")),
                byte_count=int(it.get("byte_count", 0)),
                requested_by=str(it.get("requested_by", node)),
            )
            for it in items
            if str(it.get("retrieval_strategy", "")).upper() == "FULL_FILE"
        ]
        receipt = ContextReceipt(
            receipt_id=f"rcpt-{uuid4().hex[:12]}",
            request_id=request_id,
            workflow=workflow,
            node=node,
            task=task,
            decision_dependency=str(items[0].get("decision_dependency", "")) if items else "",
            envelope_hash=_envelope_hash(envelope),
            ranking_hash=_ranking_hash(envelope.items),
            budget_hash=_budget_hash(budget),
            included_refs=included_refs,
            omitted_refs=omitted_refs,
            used_tokens=envelope.tokens_used,
            available_tokens=budget,
            confidence=_confidence(envelope.items),
            full_file_reads=full_file_reads,
            created_at=datetime.now(UTC),
        )
        return ContextBuildResult(envelope=envelope, receipt=receipt)


__all__ = ["ContextBuildResult", "ContextEngine", "ResourceBudget"]
