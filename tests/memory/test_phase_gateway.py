"""PhaseMemoryGateway — per-phase recall/persist enforcing PHASE_MEMORY_POLICY.

The gateway is the ONE shared service that reads memory before a phase runs and
persists after, honouring the (previously metadata-only) ``phase_policy``:

- ``recall(phase, query)`` searches EXACTLY the phase's declared ``read_layers``.
- ``persist(phase, outcome)`` writes EXACTLY the phase's declared ``write_layers``.
- ``require_approval`` maps onto the native ``MemoryRecord`` lifecycle:
  False → ``lifecycle=ACTIVE``; True → ``lifecycle=CANDIDATE`` + ``status=STALE``
  (persisted-but-"needs review", never dropped).
- ``recall`` partitions hits into ``trusted`` (active) vs ``needs_review``.
- An unknown phase and a Null store are safe no-ops (never raise).

These tests use a recording fake that implements ONLY the real store port
surface (``search(query, scope, limit)`` + ``write(record)``). The gateway is the
sole phase-boundary memory path; it superseded and retired the old
``MemoryCaptureService`` (removed), which called a non-existent ``.store()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from opencontext_core.memory.agent import NullAgentMemoryStore
from opencontext_core.memory.phase_gateway import PhaseMemoryGateway
from opencontext_core.memory.phase_policy import PHASE_MEMORY_POLICY
from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryLifecycle,
    MemoryRecord,
    MemoryStatus,
)


def _rec(
    layer: MemoryLayer,
    *,
    content: str = "x",
    lifecycle: MemoryLifecycle = MemoryLifecycle.ACTIVE,
    status: MemoryStatus = MemoryStatus.ACTIVE,
    rid: str = "r0",
) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=rid,
        layer=layer,
        key=f"k:{rid}",
        content=content,
        decay_policy=DecayPolicy(enabled=False),
        created_at=now,
        updated_at=now,
        lifecycle=lifecycle,
        status=status,
    )


@dataclass
class RecordingStore:
    """Fake that records every search()/write() call over the REAL port surface."""

    searches: list[tuple[str, MemoryLayer | None, int]] = field(default_factory=list)
    writes: list[MemoryRecord] = field(default_factory=list)
    # Optional canned results keyed by the searched layer.
    results_by_layer: dict[MemoryLayer | None, list[MemoryRecord]] = field(default_factory=dict)

    def search(
        self, query: str, *, scope: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]:
        self.searches.append((query, scope, limit))
        return list(self.results_by_layer.get(scope, []))

    def write(self, memory: MemoryRecord) -> str:
        self.writes.append(memory)
        return memory.id


# ---------------------------------------------------------------------------
# recall reads EXACTLY the declared read_layers
# ---------------------------------------------------------------------------


def test_recall_searches_exactly_declared_read_layers_for_spec() -> None:
    """spec.read_layers == (SEMANTIC, WORKING) → those two scopes, nothing else."""
    store = RecordingStore()
    gw = PhaseMemoryGateway(store)

    gw.recall("spec", "improve authenticate", limit=5)

    searched_layers = {scope for (_q, scope, _lim) in store.searches}
    assert searched_layers == {MemoryLayer.SEMANTIC, MemoryLayer.WORKING}
    # exactly one search per declared read layer, no scope=None whole-store sweep
    assert len(store.searches) == len(PHASE_MEMORY_POLICY["spec"].read_layers)
    assert None not in searched_layers
    # query + limit forwarded verbatim
    assert all(q == "improve authenticate" and lim == 5 for (q, _s, lim) in store.searches)


def test_recall_reads_explore_layers_semantic_and_episodic() -> None:
    store = RecordingStore()
    gw = PhaseMemoryGateway(store)

    gw.recall("explore", "task")

    searched = {scope for (_q, scope, _lim) in store.searches}
    assert searched == {MemoryLayer.SEMANTIC, MemoryLayer.EPISODIC}


# ---------------------------------------------------------------------------
# persist writes EXACTLY the declared write_layers
# ---------------------------------------------------------------------------


def test_persist_writes_exactly_declared_write_layers_for_apply() -> None:
    """apply.write_layers == (EPISODIC, FAILURE) on a passing outcome."""
    store = RecordingStore()
    gw = PhaseMemoryGateway(store)

    gw.persist("apply", PhaseMemoryGateway.outcome(content="applied", failed=False))

    written_layers = {rec.layer for rec in store.writes}
    assert written_layers == {MemoryLayer.EPISODIC, MemoryLayer.FAILURE}
    assert len(store.writes) == len(PHASE_MEMORY_POLICY["apply"].write_layers)
    assert all(rec.content == "applied" for rec in store.writes)


def test_persist_writes_working_only_for_tasks() -> None:
    store = RecordingStore()
    gw = PhaseMemoryGateway(store)

    gw.persist("tasks", PhaseMemoryGateway.outcome(content="broke it down", failed=False))

    assert {rec.layer for rec in store.writes} == {MemoryLayer.WORKING}


def test_apply_failed_outcome_persists_a_failure_layer_record() -> None:
    """A FAILED apply outcome MUST land a FAILURE-layer record (recent-failure boost)."""
    store = RecordingStore()
    gw = PhaseMemoryGateway(store)

    gw.persist("apply", PhaseMemoryGateway.outcome(content="tests red", failed=True))

    failure_records = [rec for rec in store.writes if rec.layer is MemoryLayer.FAILURE]
    assert failure_records, "failed apply did not persist a FAILURE-layer record"


# ---------------------------------------------------------------------------
# require_approval → lifecycle/status mapping
# ---------------------------------------------------------------------------


def test_require_approval_false_writes_active() -> None:
    """explore.require_approval is False → lifecycle ACTIVE + status ACTIVE."""
    store = RecordingStore()
    gw = PhaseMemoryGateway(store)

    gw.persist("explore", PhaseMemoryGateway.outcome(content="explored", failed=False))

    assert store.writes, "explore should persist to its working layer"
    for rec in store.writes:
        assert rec.lifecycle is MemoryLifecycle.ACTIVE
        assert rec.status is MemoryStatus.ACTIVE


def test_require_approval_true_writes_candidate_stale() -> None:
    """spec.require_approval is True → lifecycle CANDIDATE + status STALE (needs review)."""
    store = RecordingStore()
    gw = PhaseMemoryGateway(store)

    gw.persist("spec", PhaseMemoryGateway.outcome(content="spec drafted", failed=False))

    assert store.writes
    for rec in store.writes:
        assert rec.lifecycle is MemoryLifecycle.CANDIDATE
        assert rec.status is MemoryStatus.STALE


def test_explicit_approval_required_override_forces_candidate() -> None:
    """Runner-resolved approval_required=True overrides a phase whose policy is False."""
    store = RecordingStore()
    gw = PhaseMemoryGateway(store, approval_required=True)

    gw.persist("explore", PhaseMemoryGateway.outcome(content="explored", failed=False))

    assert store.writes
    for rec in store.writes:
        assert rec.lifecycle is MemoryLifecycle.CANDIDATE
        assert rec.status is MemoryStatus.STALE


# ---------------------------------------------------------------------------
# recall partitions trusted vs needs_review
# ---------------------------------------------------------------------------


def test_recall_partitions_needs_review_vs_trusted() -> None:
    store = RecordingStore()
    trusted = _rec(
        MemoryLayer.SEMANTIC,
        content="trusted fact",
        lifecycle=MemoryLifecycle.ACTIVE,
        status=MemoryStatus.ACTIVE,
        rid="ok",
    )
    stale = _rec(
        MemoryLayer.SEMANTIC,
        content="stale belief",
        lifecycle=MemoryLifecycle.CANDIDATE,
        status=MemoryStatus.STALE,
        rid="review",
    )
    store.results_by_layer[MemoryLayer.SEMANTIC] = [trusted, stale]
    gw = PhaseMemoryGateway(store)

    result = gw.recall("spec", "query")

    trusted_ids = {r.id for r in result.trusted}
    review_ids = {r.id for r in result.needs_review}
    assert "ok" in trusted_ids
    assert "review" in review_ids
    assert "review" not in trusted_ids


# ---------------------------------------------------------------------------
# safety: unknown phase + Null store never raise
# ---------------------------------------------------------------------------


def test_unknown_phase_recall_is_noop_zero_searches() -> None:
    store = RecordingStore()
    gw = PhaseMemoryGateway(store)

    result = gw.recall("gga", "anything")

    assert store.searches == []
    assert result.trusted == []
    assert result.needs_review == []


def test_unknown_phase_persist_is_noop_zero_writes() -> None:
    store = RecordingStore()
    gw = PhaseMemoryGateway(store)

    gw.persist("judgment", PhaseMemoryGateway.outcome(content="c", failed=False))

    assert store.writes == []


def test_null_store_recall_and_persist_do_not_raise() -> None:
    gw = PhaseMemoryGateway(NullAgentMemoryStore())

    result = gw.recall("spec", "q")
    gw.persist("spec", PhaseMemoryGateway.outcome(content="c", failed=False))

    assert result.trusted == []
    assert result.needs_review == []


def test_none_store_is_treated_as_null_noop() -> None:
    """A missing store (None) must be tolerated exactly like the Null store."""
    gw = PhaseMemoryGateway(None)

    result = gw.recall("spec", "q")
    gw.persist("spec", PhaseMemoryGateway.outcome(content="c", failed=False))

    assert result.trusted == []
    assert result.needs_review == []


def test_recall_result_render_surfaces_needs_review() -> None:
    """The recall block fed into a prompt must flag needs_review context as stale."""
    store = RecordingStore()
    store.results_by_layer[MemoryLayer.SEMANTIC] = [
        _rec(MemoryLayer.SEMANTIC, content="trusted fact", rid="ok"),
        _rec(
            MemoryLayer.SEMANTIC,
            content="stale belief",
            lifecycle=MemoryLifecycle.CANDIDATE,
            status=MemoryStatus.STALE,
            rid="review",
        ),
    ]
    gw = PhaseMemoryGateway(store)

    block = gw.recall("spec", "query").render()

    assert "trusted fact" in block
    assert "stale belief" in block
    # the render must not silently present needs_review content as trusted
    assert "needs review" in block.lower() or "needs_review" in block.lower()


def test_search_failure_is_swallowed_returns_empty() -> None:
    """A store that raises on search must not blow up the phase (memory is optional)."""

    class Boom:
        def search(self, *_a: Any, **_k: Any) -> list[MemoryRecord]:
            raise RuntimeError("store down")

        def write(self, memory: MemoryRecord) -> str:
            raise RuntimeError("store down")

    gw = PhaseMemoryGateway(Boom())
    result = gw.recall("spec", "q")
    gw.persist("spec", PhaseMemoryGateway.outcome(content="c", failed=False))
    assert result.trusted == []
    assert result.needs_review == []
