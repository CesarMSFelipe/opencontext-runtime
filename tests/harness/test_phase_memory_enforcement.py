"""Every SDD phase recalls its read_layers and persists its write_layers.

Group B of the memory-wiring slice: the HarnessRunner phase loop must drive a
shared ``PhaseMemoryGateway`` so that — for a real ``sdd`` run — each phase in
PHASE_ORDER issues a recall over exactly its declared ``read_layers`` and a
write over exactly its declared ``write_layers`` (from ``PHASE_MEMORY_POLICY``).
It must also inject the recalled memory into the middle phases' executor
``context`` so the model prompts actually see it.

The store is injected via ``HarnessRunner(..., memory_store=<recording fake>)``;
the fake implements ONLY the real port surface (``search`` + ``write``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opencontext_core.agents.sdd_orchestrator import PHASE_ORDER
from opencontext_core.harness.models import BudgetMode
from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.memory.phase_policy import PHASE_MEMORY_POLICY
from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryRecord,
)


@dataclass
class RecordingStore:
    """Recording fake over the real AgentMemoryStore port surface."""

    searches: list[tuple[str, MemoryLayer | None, int]] = field(default_factory=list)
    writes: list[MemoryRecord] = field(default_factory=list)
    canned: str = ""

    def search(
        self, query: str, *, scope: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]:
        self.searches.append((query, scope, limit))
        if not self.canned:
            return []
        from datetime import UTC, datetime

        now = datetime.now(tz=UTC)
        return [
            MemoryRecord(
                id=f"canned-{scope}",
                layer=scope or MemoryLayer.SEMANTIC,
                key="canned:0",
                content=self.canned,
                decay_policy=DecayPolicy(enabled=False),
                created_at=now,
                updated_at=now,
            )
        ]

    def write(self, memory: MemoryRecord) -> str:
        self.writes.append(memory)
        return memory.id

    # Unused-but-present methods so the fake satisfies the whole port.
    def reinforce(self, *_a: Any, **_k: Any) -> None:
        return None

    def contradict(self, *_a: Any, **_k: Any) -> None:
        return None

    def decay(self) -> int:
        return 0

    def failure_boost(self, *_a: Any, **_k: Any) -> dict[str, float]:
        return {}


@dataclass
class CapturingDelegate:
    """Fake executor: records the context dict handed to each phase and succeeds."""

    contexts: dict[str, dict[str, Any]] = field(default_factory=dict)

    def delegate(self, phase: str, context: dict[str, Any]) -> Any:
        self.contexts[phase] = context

        class _R:
            status = "success"
            output = f"executor output for {phase}"
            error = None

        return _R()


def _searched_layers(store: RecordingStore) -> set[MemoryLayer]:
    return {scope for (_q, scope, _lim) in store.searches if scope is not None}


def test_each_sdd_phase_recalls_its_read_layers(tmp_path: Path) -> None:
    (tmp_path / "auth.py").write_text("def auth(u, p):\n    return u == p\n", encoding="utf-8")
    store = RecordingStore()
    runner = HarnessRunner(root=tmp_path, memory_store=store)

    runner.run(
        "sdd",
        "improve authenticate password hashing",
        BudgetMode.WARN,
        approved_phases={"apply"},
    )

    # Aggregate: the union of everything searched must cover each phase's read
    # layers. (Layers overlap across phases, so we verify coverage of the union
    # of all PHASE_ORDER read layers rather than per-call attribution here.)
    expected_read_union: set[MemoryLayer] = set()
    for phase in PHASE_ORDER:
        expected_read_union |= set(PHASE_MEMORY_POLICY[phase].read_layers)

    searched = _searched_layers(store)
    missing = expected_read_union - searched
    assert not missing, f"phases never recalled these read layers: {missing}"


def test_each_sdd_phase_persists_its_write_layers(tmp_path: Path) -> None:
    (tmp_path / "auth.py").write_text("def auth(u, p):\n    return u == p\n", encoding="utf-8")
    store = RecordingStore()
    runner = HarnessRunner(root=tmp_path, memory_store=store)

    runner.run(
        "sdd",
        "improve authenticate password hashing",
        BudgetMode.WARN,
        approved_phases={"apply"},
    )

    expected_write_union: set[MemoryLayer] = set()
    for phase in PHASE_ORDER:
        expected_write_union |= set(PHASE_MEMORY_POLICY[phase].write_layers)

    written = {rec.layer for rec in store.writes}
    missing = expected_write_union - written
    assert not missing, f"phases never persisted these write layers: {missing}"


def test_recall_count_matches_read_layer_cardinality(tmp_path: Path) -> None:
    """The gateway must issue one SCOPED search per declared read layer per phase.

    The runner's memory store is shared: ExplorePhase's own recall and the
    harvester also hit it, but ALWAYS with ``scope=None`` (whole-store sweeps).
    The PhaseMemoryGateway is the only consumer that searches with a concrete
    layer scope, so the count of scoped searches must equal the sum of
    ``read_layers`` over PHASE_ORDER (each phase runs once in a fresh sdd run).
    """
    (tmp_path / "auth.py").write_text("def auth(u, p):\n    return u == p\n", encoding="utf-8")
    store = RecordingStore()
    runner = HarnessRunner(root=tmp_path, memory_store=store)

    runner.run(
        "sdd",
        "improve authenticate hashing",
        BudgetMode.WARN,
        approved_phases={"apply"},
    )

    scoped = [scope for (_q, scope, _lim) in store.searches if scope is not None]
    expected_searches = sum(len(PHASE_MEMORY_POLICY[p].read_layers) for p in PHASE_ORDER)
    assert len(scoped) == expected_searches, (
        f"expected {expected_searches} scoped searches (sum of read_layers over "
        f"PHASE_ORDER), got {len(scoped)}"
    )


def test_middle_phase_executor_context_contains_recalled_memory(tmp_path: Path) -> None:
    """A middle phase's executor context dict must include the recalled memory text."""
    (tmp_path / "auth.py").write_text("def auth(u, p):\n    return u == p\n", encoding="utf-8")
    store = RecordingStore(canned="RECALLED-MEMORY-SENTINEL bcrypt rule")
    delegate = CapturingDelegate()
    runner = HarnessRunner(root=tmp_path, memory_store=store)

    # Attach the capturing executor so spec/design/tasks run through it.
    orig_create = runner.create_run

    def _create(workflow: str, task: str):
        st = orig_create(workflow, task)
        st.delegate = delegate
        return st

    runner.create_run = _create  # type: ignore[method-assign]

    runner.run(
        "sdd",
        "improve authenticate hashing",
        BudgetMode.WARN,
        approved_phases={"apply"},
    )

    # At least one middle phase (spec/design/tasks) went through the executor.
    middle = {"spec", "design", "tasks"} & set(delegate.contexts)
    assert middle, f"no middle phase reached the executor; saw {list(delegate.contexts)}"

    # The recalled sentinel must appear in that phase's executor context blob.
    found = any(
        "RECALLED-MEMORY-SENTINEL" in str(delegate.contexts[p].get("context", "")) for p in middle
    )
    assert found, (
        "recalled memory was not injected into any middle phase's executor context; "
        f"contexts keys={list(delegate.contexts)}"
    )
