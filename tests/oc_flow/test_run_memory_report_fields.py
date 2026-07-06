"""run.json memory block: new_candidates + requires_approval (MEMORY_CONTRACT rule 4).

MEM-HITS-SHAPE: a run that uses memory reports
``{memory: {used, hits, new_candidates, requires_approval}}``. The hits shape
is pinned by test_run_bundle_memory.py; this pins the two candidate-accounting
fields and their consolidation-side producer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    node_consolidation,
)
from opencontext_core.oc_flow.run_bundle import memory_block


class _CapturingStore:
    """Minimal AgentMemoryStore double: canned search, captured writes."""

    def __init__(self) -> None:
        self.written: list[MemoryRecord] = []

    def search(self, query: str, *, scope: object = None, limit: int = 10) -> list[MemoryRecord]:
        return []

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


def _record(key: str) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=f"mem-{key}",
        layer=MemoryLayer.SEMANTIC,
        key=key,
        content="content",
        confidence=0.8,
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
    )
    for name, value in overrides.items():
        setattr(ctx, name, value)
    return ctx


def test_memory_block_defaults_report_zero_candidates() -> None:
    """MEM-HITS-SHAPE: the memory block always carries the two candidate fields."""
    assert memory_block([]) == {
        "used": False,
        "hits": [],
        "new_candidates": 0,
        "requires_approval": False,
    }


def test_memory_block_reports_candidates_and_approval() -> None:
    """MEM-HITS-SHAPE: new_candidates and requires_approval are reported verbatim."""
    hits = [{"id": "7", "type": "project_context", "score": 0.5, "used_for": "context_pack"}]
    block = memory_block(hits, new_candidates=2, requires_approval=True)
    assert block == {
        "used": True,
        "hits": hits,
        "new_candidates": 2,
        "requires_approval": True,
    }


def test_consolidation_counts_harvested_candidates(tmp_path: Path) -> None:
    """MEM-HITS-SHAPE: consolidation records how many candidates the run harvested."""
    store = _CapturingStore()
    ctx = _ctx(
        tmp_path,
        memory_enabled=True,
        memory_store=store,
        memory_harvest_enabled=True,
        memory_v2_enabled=True,
        run_id="run-mem-hits",
    )
    ctx.changed_files = ["pkg/mod.py"]
    node_consolidation(ctx)

    assert ctx.memory_new_candidates > 0
    assert ctx.memory_new_candidates >= len(store.written) > 0


def test_consolidation_without_harvest_reports_zero_candidates(tmp_path: Path) -> None:
    """MEM-HITS-SHAPE: with harvest disabled the run reports zero new candidates."""
    ctx = _ctx(tmp_path)  # memory disabled (default)
    ctx.changed_files = ["pkg/mod.py"]
    node_consolidation(ctx)
    assert ctx.memory_new_candidates == 0
