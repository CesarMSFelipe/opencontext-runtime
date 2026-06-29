"""Budgeted, ordered memory retrieval keyed by ``MemoryQuery`` (book §11/§12).

Memory is L4 and must not import the Context engine (L5); token estimation here
is a local heuristic so this module stays dependency-free of Context. Retrieval
follows the book order — exact-tags → procedural → failure → semantic → episodic
— accumulating records until the node's record/token budget is hit, and emits the
``memory.retrieved`` event.
"""

from __future__ import annotations

from opencontext_core.memory.events import MemoryEvent, MemoryEventEmitter
from opencontext_core.models.agent_memory import MemoryLayer, MemoryRecord
from opencontext_core.models.memory import MemoryQuery

# Book §11 retrieval order after the exact-tag pass.
_RETRIEVAL_ORDER: tuple[MemoryLayer, ...] = (
    MemoryLayer.PROCEDURAL,
    MemoryLayer.FAILURE,
    MemoryLayer.SEMANTIC,
    MemoryLayer.EPISODIC,
)

# Book §12 per-node budgets: (workflow, node) -> (max_records, max_tokens).
# Conservative defaults; callers may always override via the MemoryQuery fields.
_NODE_BUDGETS: dict[tuple[str, str], tuple[int, int]] = {
    ("oc-flow", "gather_context"): (8, 2000),
    ("oc-flow", "plan"): (5, 1200),
    ("oc-flow", "implement"): (4, 1000),
    ("oc-flow", "verify"): (4, 800),
}
_DEFAULT_BUDGET: tuple[int, int] = (8, 2000)


def node_budget(workflow: str, node: str) -> tuple[int, int]:
    """Return ``(max_records, max_tokens)`` for a workflow/node (book §12)."""
    return _NODE_BUDGETS.get((workflow, node), _DEFAULT_BUDGET)


def query_for_node(
    task: str, workflow: str, node: str, *, tags: list[str] | None = None
) -> MemoryQuery:
    """Build a budget-bound :class:`MemoryQuery` for a workflow/node."""
    max_records, max_tokens = node_budget(workflow, node)
    return MemoryQuery(
        task=task,
        workflow=workflow,
        node=node,
        tags=tags or [],
        max_records=max_records,
        max_tokens=max_tokens,
    )


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token); local to avoid a Context import."""
    return max(1, len(text) // 4)


# Execution-profile tuning (PR-009 MEM-CONV profile-aware retrieval, PR-000.2
# profiles): (record_multiplier, token_multiplier, min_confidence_floor).
_PROFILE_TUNING: dict[str, tuple[float, float, float]] = {
    "low-cost": (0.5, 0.5, 0.1),
    "balanced": (1.0, 1.0, 0.0),
    "enterprise": (1.5, 1.5, 0.0),
    "research": (2.0, 2.0, 0.0),
    "performance": (0.75, 0.75, 0.2),
}


def apply_profile(query: MemoryQuery, profile: str | None) -> MemoryQuery:
    """Tune a query's record/token budget and min-confidence for an execution profile.

    Unknown/empty profiles return the query unchanged (legacy behavior).
    """
    if not profile:
        return query
    record_mult, token_mult, min_conf_floor = _PROFILE_TUNING.get(profile, (1.0, 1.0, 0.0))
    return query.model_copy(
        update={
            "max_records": max(1, int(query.max_records * record_mult)),
            "max_tokens": max(1, int(query.max_tokens * token_mult)),
            "min_confidence": max(query.min_confidence, min_conf_floor),
        }
    )


def retrieve_memory(
    store: object,
    query: MemoryQuery,
    *,
    emitter: MemoryEventEmitter | None = None,
) -> list[MemoryRecord]:
    """Retrieve records for ``query`` honoring its budgets and the book order."""
    selected: list[MemoryRecord] = []
    seen: set[str] = set()
    tokens = 0

    def consider(rec: MemoryRecord) -> None:
        nonlocal tokens
        if rec.id in seen:
            return
        if rec.confidence < query.min_confidence:
            return
        if len(selected) >= query.max_records:
            return
        cost = estimate_tokens(rec.content)
        if tokens + cost > query.max_tokens:
            return
        selected.append(rec)
        seen.add(rec.id)
        tokens += cost

    def budget_left() -> bool:
        return len(selected) < query.max_records and tokens < query.max_tokens

    search = getattr(store, "search", None)
    if callable(search):
        # 1. exact-tag matches first (highest-precision recall).
        if query.tags and budget_left():
            wanted = set(query.tags)
            try:
                for rec in search(query.task, limit=max(query.max_records * 4, 8)):
                    if wanted & set(getattr(rec, "tags", [])):
                        consider(rec)
            except Exception:
                pass
        # 2. then by layer in the documented order.
        for layer in _RETRIEVAL_ORDER:
            if not budget_left():
                break
            try:
                for rec in search(query.task, scope=layer, limit=max(query.max_records * 2, 4)):
                    consider(rec)
            except TypeError:
                continue
            except Exception:
                continue

    if emitter is not None:
        emitter.emit(
            MemoryEvent.RETRIEVED,
            task=query.task,
            workflow=query.workflow,
            node=query.node,
            records=len(selected),
            tokens=tokens,
        )
    return selected
