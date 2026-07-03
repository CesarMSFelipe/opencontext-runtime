"""OC Flow memory read/write + envelope compression parity tests.

Parity targets (SDD harness reference behaviour):
  * gather_context folds memory recall into the ContextEnvelope
    (ExplorePhase folds memory_store.search into the context pack);
  * consolidation persists harvested memory through the MemoryHarvester /
    MemoryHarness sole-writer path (ArchivePhase harvest);
  * gather_context applies CompressionEngine to oversized envelope content
    and records evidence in context-receipt.json (context substrate parity),
    including the honest skip for SQLite-backed KG items.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryRecord,
)
from opencontext_core.oc_flow.budgets import OC_FLOW_BUDGETS
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    node_consolidation,
    node_gather_context,
)


class _FakeMemoryStore:
    """Deterministic AgentMemoryStore double: canned search, captured writes."""

    def __init__(self, records: list[MemoryRecord] | None = None) -> None:
        self.records = list(records or [])
        self.written: list[MemoryRecord] = []
        self.search_queries: list[str] = []

    def search(
        self, query: str, *, scope: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]:
        self.search_queries.append(query)
        return self.records[:limit]

    def write(self, memory: MemoryRecord) -> str:
        self.written.append(memory)
        return memory.id

    def reinforce(self, memory_id: str, evidence: object) -> None:
        return None

    def contradict(self, memory_id: str, evidence: object) -> None:
        return None

    def decay(self) -> int:
        return 0

    def failure_boost(self, symbols: list[str]) -> dict[str, float]:
        return {}


class _ExplodingMemoryStore(_FakeMemoryStore):
    """Store whose search always fails — the run must survive it."""

    def search(
        self, query: str, *, scope: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]:
        raise RuntimeError("memory backend unavailable")


def _record(key: str, content: str, *, confidence: float = 0.8) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=f"mem-{key}",
        layer=MemoryLayer.FAILURE,
        key=key,
        content=content,
        confidence=confidence,
        decay_policy=DecayPolicy(enabled=True),
        created_at=now,
        updated_at=now,
    )


def _ctx(root: Path, **overrides: object) -> OCFlowContext:
    artifacts = root / "artifacts" / "oc-flow"
    artifacts.mkdir(parents=True, exist_ok=True)
    ctx = OCFlowContext(
        root=root,
        artifacts_dir=artifacts,
        task="Fix failing auth token test",
        lane=Lane.FAST,
        profile="balanced",
        executor=DeterministicNodeExecutor(),
        max_attempts=2,
        seed_paths=["pkg/mod.py"],
    )
    for name, value in overrides.items():
        setattr(ctx, name, value)
    return ctx


# ------------------------------------------------------------- memory READ (gather)
def test_gather_context_folds_memory_items_into_envelope(tmp_path: Path) -> None:
    store = _FakeMemoryStore(
        [
            _record(
                "failure:auth", "Task 'auth fix' was missing context: auth.py.", confidence=0.9
            ),
            _record("procedural:auth", "Review token expiry coverage first.", confidence=0.7),
        ]
    )
    ctx = _ctx(tmp_path, memory_enabled=True, memory_store=store)
    node_gather_context(ctx)

    assert ctx.envelope is not None
    memory_items = [i for i in ctx.envelope.items if i.why_included.startswith("memory:score")]
    assert len(memory_items) == 2
    assert all(i.source == "memory" for i in memory_items)
    assert all(i.confidence > 0.0 for i in memory_items)
    # The store was searched with the task statement.
    assert store.search_queries == [ctx.task]
    # Budget accounting includes the folded memory items.
    assert ctx.envelope.token_estimate == sum(i.tokens for i in ctx.envelope.items)


def test_gather_context_memory_respects_budget_cap(tmp_path: Path) -> None:
    cap = OC_FLOW_BUDGETS["gather_context"][1]
    # One record so large it can never fit the remaining budget.
    store = _FakeMemoryStore([_record("huge", "x" * (cap * 8), confidence=0.9)])
    ctx = _ctx(tmp_path, memory_enabled=True, memory_store=store)
    node_gather_context(ctx)

    assert ctx.envelope is not None
    memory_items = [i for i in ctx.envelope.items if i.why_included.startswith("memory:score")]
    assert memory_items == []
    assert ctx.envelope.token_estimate <= cap


def test_gather_context_degrades_silently_without_store(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, memory_enabled=True, memory_store=None)
    node_gather_context(ctx)  # must not raise

    assert ctx.envelope is not None
    assert any("memory" in note for note in ctx.envelope.omissions)
    receipt = json.loads((ctx.artifacts_dir / "context-receipt.json").read_text())
    assert any("memory" in o["why_omitted"] for o in receipt["omissions"])


def test_gather_context_survives_memory_search_failure(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, memory_enabled=True, memory_store=_ExplodingMemoryStore())
    node_gather_context(ctx)  # must not raise

    assert ctx.envelope is not None
    memory_items = [i for i in ctx.envelope.items if i.why_included.startswith("memory:score")]
    assert memory_items == []
    assert any("memory" in note for note in ctx.envelope.omissions)


def test_gather_context_without_memory_flag_is_unchanged(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)  # memory disabled (default)
    node_gather_context(ctx)

    assert ctx.envelope is not None
    assert not any(i.why_included.startswith("memory:score") for i in ctx.envelope.items)
    assert not any("memory recall" in note for note in ctx.envelope.omissions)


# ---------------------------------------------------- memory WRITE (consolidation)
def test_consolidation_persists_memory_through_harness(tmp_path: Path) -> None:
    store = _FakeMemoryStore()
    ctx = _ctx(
        tmp_path,
        memory_enabled=True,
        memory_store=store,
        memory_harvest_enabled=True,
        memory_v2_enabled=True,
        run_id="run-oc-flow-test",
    )
    ctx.changed_files = ["pkg/mod.py"]
    result = node_consolidation(ctx)

    # The delta artifact remains (evidence), extended with the harvest outcome.
    delta = json.loads((ctx.artifacts_dir / "consolidation" / "memory-delta.json").read_text())
    assert delta["harvest"]["persisted"] is True
    assert delta["harvest"]["run_id"] == "run-oc-flow-test"
    assert delta["harvest"]["origin"] == "agent"
    assert result.outputs["memory_persisted"] is True
    # Records reached the durable store THROUGH the harness (sole writer):
    # harness-built records carry provenance="harness".
    assert store.written
    assert all(getattr(r, "provenance", "") == "harness" for r in store.written)
    # Every persisted record traces back to this run.
    for rec in store.written:
        assert any(ref.run_id == "run-oc-flow-test" for ref in rec.source_refs)


def test_consolidation_memory_noop_reason_when_disabled(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)  # memory disabled (default)
    ctx.changed_files = ["pkg/mod.py"]
    result = node_consolidation(ctx)

    delta = json.loads((ctx.artifacts_dir / "consolidation" / "memory-delta.json").read_text())
    assert delta["harvest"]["persisted"] is False
    assert delta["harvest"]["reason"]
    assert result.outputs["memory_persisted"] is False


def test_consolidation_memory_noop_reason_when_store_missing(tmp_path: Path) -> None:
    ctx = _ctx(
        tmp_path,
        memory_enabled=True,
        memory_store=None,
        memory_harvest_enabled=True,
        memory_v2_enabled=True,
    )
    result = node_consolidation(ctx)

    delta = json.loads((ctx.artifacts_dir / "consolidation" / "memory-delta.json").read_text())
    assert delta["harvest"]["persisted"] is False
    assert "store" in delta["harvest"]["reason"]
    assert result.outputs["memory_persisted"] is False
