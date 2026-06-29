"""The Context Engine — single build entrypoint for a workflow node (PR-010).

Composes the existing substrate (it does not rewrite it): it selects a
:class:`RetrievalStrategy`, resolves the per-node budget, runs the existing
``plan() -> select_diverse() -> pack()`` pipeline, assembles the typed three-layer
:class:`ContextEnvelope`, validates ``token_estimate`` against the budget (reusing
``harness/budget.py:TokenBudgetEnforcer``), fires compression then incremental GC on
overflow, and emits the four typed receipts out-of-band. SDD and OC Flow share this
one engine (book §Definition of Done).

Behind ``runtime.context_engine_enabled`` (default off): the legacy direct
``ProjectRetriever.plan()`` → ``ContextPackBuilder.pack()`` path stays the default, so
nothing changes unless a caller opts into the engine.

Layering (doc 58): Context Engine is L5 — it sits ABOVE KG/Memory/Cache/Compression
(L4) and may use all of them; it produces the :class:`ContextEnvelope`. The surgical
OC Flow projection (PR-007 seam) is derived here via :func:`to_surgical_envelope`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from opencontext_core.context.budget_table import resolve as resolve_budget
from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.context.compression import CompressionEngine
from opencontext_core.context.gc import GcAttempt, GcTrigger, collect
from opencontext_core.context.packing import ContextPackBuilder
from opencontext_core.context.profiles import ProfileSettings, resolve_profile
from opencontext_core.context.ranking import attach_usefulness
from opencontext_core.context.receipt import (
    BudgetDecision,
    BudgetReceipt,
    CompressionReceipt,
    OmissionReceipt,
    QueryReceipt,
    RetrievalReceipts,
)
from opencontext_core.context.strategies import reorder, select_strategy
from opencontext_core.harness.budget import TokenBudgetEnforcer
from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.models.context import (
    CompressionStrategy,
    ContextItem,
    ContextOmission,
    ContextProfile,
)
from opencontext_core.models.context_envelope import ContextEnvelope
from opencontext_core.models.evidence import EvidenceRef

if TYPE_CHECKING:
    # The OC Flow surgical envelope (L9) is a projection of the canonical envelope.
    # Imported only for typing — annotations are lazy strings (PEP 563), so this L5
    # module still pulls no L9 code at import time.
    from opencontext_core.oc_flow.models import ContextEnvelope as SurgicalEnvelope


@dataclass
class ContextBuildResult:
    """The engine result: the typed envelope plus out-of-band receipts.

    Receipts and GC output are carried *beside* the envelope, never injected into the
    prompt body — they must not consume the budget they account for (design #9).
    """

    envelope: ContextEnvelope
    receipts: RetrievalReceipts
    cache_hit: bool = False
    gc_output: str = ""
    cache_provenance: dict[str, Any] | None = None
    discarded_l1_keys: list[str] = field(default_factory=list)


class ContextEngine:
    """Builds a :class:`ContextEnvelope` for a workflow node (book §Context Pipeline)."""

    def __init__(
        self,
        *,
        retriever: Any | None = None,
        compression_engine: CompressionEngine | None = None,
        profile: ContextProfile | str | None = None,
        semantic_cache: Any | None = None,
        budget_mode: BudgetMode = BudgetMode.WARN,
        rerank_top_k: int = 8,
    ) -> None:
        self._retriever = retriever
        self._comp = compression_engine
        self._profile = profile
        self._cache = semantic_cache
        self._budget_mode = budget_mode
        self._rerank_top_k = rerank_top_k

    @classmethod
    def from_config(cls, config: Any, **overrides: Any) -> ContextEngine:
        """Build an engine from an ``OpenContextConfig`` (compression + profile + mode).

        The compression engine is created with ``semantic_protection=True`` so the v2
        keep/compress/discard rules apply on the engine path only.
        """
        context_cfg = getattr(config, "context", None)
        comp = None
        if context_cfg is not None:
            comp = CompressionEngine(context_cfg.compression, semantic_protection=True)
        # Prefer the context profile; fall back to the runtime execution profile.
        profile = getattr(context_cfg, "profile", None) if context_cfg is not None else None
        if profile is None:
            runtime = getattr(config, "runtime", None)
            profile = getattr(runtime, "execution_profile", None) if runtime is not None else None
        # context.budget_mode is the agentic BudgetMode enum; map it onto the harness
        # BudgetMode (off/warn/strict) the TokenBudgetEnforcer expects, by value.
        raw_mode = str(getattr(context_cfg, "budget_mode", "warn")) if context_cfg else "warn"
        try:
            budget_mode = BudgetMode(raw_mode)
        except ValueError:
            budget_mode = BudgetMode.WARN
        kwargs: dict[str, Any] = {
            "compression_engine": comp,
            "profile": profile,
            "budget_mode": budget_mode,
        }
        kwargs.update(overrides)
        return cls(**kwargs)

    # ------------------------------------------------------------------ build
    def build(
        self,
        workflow: str,
        node: str,
        task: str,
        *,
        candidates: list[ContextItem] | None = None,
        l2: dict[str, Any] | None = None,
        l3: dict[str, Any] | None = None,
        l1_working: dict[str, Any] | None = None,
        cache_key: Any | None = None,
        attempts: list[GcAttempt] | None = None,
    ) -> ContextBuildResult:
        """Build the typed envelope for ``(workflow, node, task)`` and its receipts."""
        from opencontext_core.retrieval.planner import ensure_full_file_reason, select_diverse

        strategy = select_strategy(node, task)
        budget = resolve_budget(workflow, node)
        settings = resolve_profile(self._profile)

        # 1) Semantic cache: return a prior pack on a sufficiently similar task.
        if self._cache is not None and cache_key is not None:
            cached = self._cache.lookup(cache_key, task)
            if cached is not None:
                return self._cache_result(
                    workflow, node, task, cached, strategy, budget, settings
                )

        # 2) Candidates: caller-supplied, else the retriever, else empty.
        retrieval_omissions: list[str] = []
        if candidates is None:
            candidates, retrieval_omissions = self._retrieve(task, budget)
        candidates = list(candidates)

        # 3) MMR diversity selection, then strategy re-rank (book §Retrieval).
        top_k = max(self._rerank_top_k, settings.depth * 4)
        selected = select_diverse(candidates, top_k)
        selected = reorder(selected, strategy)
        selected = [ensure_full_file_reason(item) for item in selected]

        # 4) Token-aware packing within the node budget (compression honours profile).
        comp_for_pack = self._comp if settings.compression != "off" else None
        pack = ContextPackBuilder().pack(selected, budget, compression_engine=comp_for_pack)
        included = attach_usefulness(pack.included, used=True)

        # 5) Assemble the three layers.
        l2_layer = dict(l2 or {"task": task})
        l3_layer = dict(l3 or {})
        l1_layer: dict[str, Any] = {"items": [_item_dict(i) for i in included]}
        if l1_working:
            l1_layer.update(l1_working)

        omissions = list(pack.omissions)
        omissions.extend(
            ContextOmission(item_id=reason, reason=reason, tokens=0, score=0.0)
            for reason in retrieval_omissions
        )
        token_estimate = _layer_tokens(l1_layer) + _layer_tokens(l2_layer) + _layer_tokens(l3_layer)
        envelope = ContextEnvelope(
            workflow=workflow,
            node=node,
            task=task,
            l3=l3_layer,
            l2=l2_layer,
            l1=l1_layer,
            token_estimate=token_estimate,
            evidence_refs=[_evidence_ref(i) for i in included],
            omissions=omissions,
            confidence=_confidence(included, omissions),
        )

        # 6) Validate token_estimate vs budget: compress (already in pack) then GC.
        comp_receipt = _compression_receipt(selected, included, comp_for_pack)
        envelope, decision, ledger_status, gc_output, discarded = self._enforce(
            envelope, node, budget, comp_receipt, attempts
        )

        receipts = RetrievalReceipts(
            query=QueryReceipt(
                strategy=strategy,
                sources=[i.source for i in included],
                query=task,
                candidate_count=len(candidates),
            ),
            budget=BudgetReceipt(
                token_estimate=envelope.token_estimate,
                budget=budget,
                decision=decision,
                mode=self._budget_mode.value,
                status=ledger_status,
            ),
            compression=comp_receipt,
            omission=OmissionReceipt(omissions=envelope.omissions),
        )

        # 7) Store the pack into the semantic cache for future similar tasks.
        if self._cache is not None and cache_key is not None:
            self._cache.store(cache_key, task, _envelope_cache_payload(envelope))

        return ContextBuildResult(
            envelope=envelope,
            receipts=receipts,
            cache_hit=False,
            gc_output=gc_output,
            discarded_l1_keys=discarded,
        )

    # ----------------------------------------------------------------- helpers
    def _retrieve(self, task: str, budget: int) -> tuple[list[ContextItem], list[str]]:
        """Retrieve candidates via the planner, or none when no retriever is set."""
        if self._retriever is None:
            return [], ["no_retriever_configured"]
        try:
            items = self._retriever.retrieve_context_items(task, budget)
            return list(items), []
        except AttributeError:
            return [], ["retriever_incompatible"]

    def _enforce(
        self,
        envelope: ContextEnvelope,
        node: str,
        budget: int,
        comp_receipt: CompressionReceipt,
        attempts: list[GcAttempt] | None,
    ) -> tuple[ContextEnvelope, BudgetDecision, str, str, list[str]]:
        """Enforce the node budget over the envelope token_estimate (book §Harness).

        Returns ``(envelope, decision, ledger_status, gc_output, discarded_keys)``.
        Compression already ran in the pack; on overflow incremental GC compacts L1.
        """
        enforcer = TokenBudgetEnforcer()
        used = envelope.token_estimate
        ledger = enforcer.evaluate(node, used, budget, self._budget_mode)

        compressed = comp_receipt.tokens_after < comp_receipt.tokens_before
        if used <= budget:
            decision: BudgetDecision = "compressed" if compressed else "fit"
            return envelope, decision, ledger.status.value, "", []

        # Overflow: run incremental GC over L1, then re-evaluate.
        compacted_l1, gc_output = collect(
            envelope.l1, GcTrigger.BUDGET_EXCEEDED, attempts or []
        )
        gc_meta = compacted_l1.get("_gc", {})
        discarded = list(gc_meta.get("discarded_keys", [])) if isinstance(gc_meta, dict) else []
        new_estimate = (
            _layer_tokens({k: v for k, v in compacted_l1.items() if k != "_gc"})
            + _layer_tokens(envelope.l2)
            + _layer_tokens(envelope.l3)
        )
        # Record the dropped L1 keys as explicit omissions (book §every omission).
        gc_omissions = [
            ContextOmission(item_id=f"l1:{key}", reason="gc_discarded", tokens=0, score=0.0)
            for key in discarded
        ]
        new_env = envelope.model_copy(
            update={
                "l1": compacted_l1,
                "token_estimate": new_estimate,
                "omissions": [*envelope.omissions, *gc_omissions],
            }
        )
        post_ledger = enforcer.evaluate(node, new_estimate, budget, self._budget_mode)
        decision = "gc" if new_estimate <= budget else "overflow"
        return new_env, decision, post_ledger.status.value, gc_output, discarded

    def _cache_result(
        self,
        workflow: str,
        node: str,
        task: str,
        cached_payload: str,
        strategy: Any,
        budget: int,
        settings: ProfileSettings,
    ) -> ContextBuildResult:
        """Build a result from a semantic-cache hit, carrying provenance."""
        provenance = getattr(self._cache, "last_hit_provenance", None)
        try:
            data = json.loads(cached_payload)
        except (ValueError, TypeError):
            data = {}
        envelope = ContextEnvelope(
            workflow=workflow,
            node=node,
            task=task,
            l1={"cached": True, **(data.get("l1", {}) if isinstance(data, dict) else {})},
            l2=data.get("l2", {"task": task}) if isinstance(data, dict) else {"task": task},
            l3=data.get("l3", {}) if isinstance(data, dict) else {},
            token_estimate=int(data.get("token_estimate", 0)) if isinstance(data, dict) else 0,
            confidence=float(data.get("confidence", 0.0)) if isinstance(data, dict) else 0.0,
        )
        receipts = RetrievalReceipts(
            query=QueryReceipt(strategy=strategy, sources=["semantic_cache"], query=task),
            budget=BudgetReceipt(
                token_estimate=envelope.token_estimate,
                budget=budget,
                decision="fit",
                mode=self._budget_mode.value,
                status=GateStatus.PASSED.value,
            ),
        )
        return ContextBuildResult(
            envelope=envelope,
            receipts=receipts,
            cache_hit=True,
            cache_provenance=provenance,
        )


# ---------------------------------------------------------------- assemblers
def envelope_l3_from_subgraph(subgraph: Any) -> dict[str, Any]:
    """Build the L3 structural layer from a PR-008 ``ContextSubgraph`` (KG wiring).

    Projects the typed subgraph nodes/edges/confidence into the envelope's book
    ``dict`` wire shape. Accepts any object exposing ``nodes``/``edges``/``confidence``
    so this stays decoupled from the KG package internals.
    """
    nodes = getattr(subgraph, "nodes", []) or []
    edges = getattr(subgraph, "edges", []) or []
    return {
        "kg_nodes": [
            {
                "id": getattr(n, "id", ""),
                "name": getattr(n, "name", ""),
                "type": getattr(getattr(n, "type", None), "value", str(getattr(n, "type", ""))),
                "path": getattr(n, "path", None),
            }
            for n in nodes
        ],
        "kg_edges": [
            {
                "source": getattr(e, "source_id", ""),
                "target": getattr(e, "target_id", ""),
                "type": getattr(getattr(e, "type", None), "value", str(getattr(e, "type", ""))),
            }
            for e in edges
        ],
        "confidence": float(getattr(subgraph, "confidence", 0.0)),
    }


def to_surgical_envelope(envelope: ContextEnvelope) -> SurgicalEnvelope:
    """Project the canonical envelope onto the OC Flow surgical seam (PR-007).

    Reconciliation: there is one canonical :class:`ContextEnvelope`; the OC Flow
    ``ContextEnvelope`` is a *projection* of it. Imported lazily so this L5 module
    does not pull OC Flow (L9) at import time.
    """
    from opencontext_core.oc_flow.models import ContextEnvelope as SurgicalEnvelope
    from opencontext_core.oc_flow.models import ContextEnvelopeItem

    items: list[ContextEnvelopeItem] = []
    for raw in envelope.l1.get("items", []) if isinstance(envelope.l1, dict) else []:
        if not isinstance(raw, dict):
            continue
        items.append(
            ContextEnvelopeItem(
                source=str(raw.get("source_type", "file")),
                ref=str(raw.get("source", "")),
                summary=str(raw.get("summary", "")),
                tokens=int(raw.get("tokens", 0)),
                full_file_reason=str(raw.get("full_file_reason", "")),
            )
        )
    return SurgicalEnvelope(
        task=envelope.task,
        items=items,
        omissions=[o.reason for o in envelope.omissions],
        token_estimate=envelope.token_estimate,
    )


def _item_dict(item: ContextItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "source": item.source,
        "source_type": item.source_type,
        "summary": str(item.metadata.get("summary", "")),
        "tokens": item.tokens,
        "usefulness": item.metadata.get("usefulness"),
        "full_file_reason": str(item.metadata.get("full_file_reason", "")),
    }


def _evidence_ref(item: ContextItem) -> EvidenceRef:
    raw = item.score if 0.0 <= item.score <= 1.0 else (item.source_trust if item.score else 0.0)
    confidence = max(0.0, min(1.0, raw))
    return EvidenceRef(
        source=item.source,
        source_type=item.source_type,
        confidence=confidence,
        path=item.source if item.source_type == "file" else None,
    )


def _layer_tokens(layer: dict[str, Any]) -> int:
    if not layer:
        return 0
    return estimate_tokens(json.dumps(layer, sort_keys=True, default=str))


def _confidence(included: list[ContextItem], omissions: list[ContextOmission]) -> float:
    if not included:
        return 0.0
    mean = sum(max(0.0, min(1.0, it.score)) for it in included) / len(included)
    penalty = min(0.2, 0.05 * len(omissions))
    return round(max(0.0, min(1.0, mean - penalty)), 6)


def _compression_receipt(
    before: list[ContextItem],
    after: list[ContextItem],
    engine: CompressionEngine | None,
) -> CompressionReceipt:
    tokens_before = sum(i.tokens for i in before)
    tokens_after = sum(i.tokens for i in after)
    strategy = (
        engine.config.strategy if engine is not None else CompressionStrategy.NONE
    )
    return CompressionReceipt(
        strategy=strategy,
        tokens_before=tokens_before,
        tokens_after=min(tokens_after, tokens_before),
    )


def _envelope_cache_payload(envelope: ContextEnvelope) -> str:
    return json.dumps(
        {
            "l1": envelope.l1,
            "l2": envelope.l2,
            "l3": envelope.l3,
            "token_estimate": envelope.token_estimate,
            "confidence": envelope.confidence,
        },
        sort_keys=True,
        default=str,
    )
