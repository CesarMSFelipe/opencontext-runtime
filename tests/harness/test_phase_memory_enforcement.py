"""Every MIDDLE SDD phase recalls its read_layers and persists its write_layers.

Group B of the memory-wiring slice: the HarnessRunner phase loop drives a shared
``PhaseMemoryGateway`` so that — for a real ``sdd`` run — each MIDDLE phase issues
a recall over exactly its declared ``read_layers`` and a write over exactly its
declared ``write_layers`` (from ``PHASE_MEMORY_POLICY``). It must also inject the
recalled memory into the middle phases' executor ``context`` so the model prompts
actually see it.

``explore`` and ``archive`` are DELIBERATELY EXCLUDED from the gateway
(``runner._MEMORY_GATEWAY_EXCLUDED_PHASES``): ExplorePhase already recalls prior
memory itself (folded into ``state.context_pack`` via a ``scope=None`` whole-store
search) and ArchivePhase already harvests/persists via the ``MemoryHarvester``.
Wrapping them in the gateway too would double-recall / double-persist — the exact
symmetric case OC Flow handles by excluding ``gather_context``/``consolidation``
from ``OC_FLOW_NODE_TO_PHASE``.

The store is injected via ``HarnessRunner(..., memory_store=<recording fake>)``;
the fake implements ONLY the real port surface (``search`` + ``write``). The
gateway is the only consumer that searches with a CONCRETE layer scope, so scoped
searches attribute cleanly to gateway recall; ExplorePhase's bespoke recall and
the harvester always sweep with ``scope=None``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opencontext_core.agents.sdd_orchestrator import PHASE_ORDER
from opencontext_core.harness.models import BudgetMode
from opencontext_core.harness.runner import _MEMORY_GATEWAY_EXCLUDED_PHASES, HarnessRunner
from opencontext_core.memory.phase_policy import PHASE_MEMORY_POLICY
from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryRecord,
)

# The phases the gateway drives: PHASE_ORDER minus the ones that own their memory.
MIDDLE_PHASES = [p for p in PHASE_ORDER if p not in _MEMORY_GATEWAY_EXCLUDED_PHASES]


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


def _scoped_searches(store: RecordingStore) -> list[MemoryLayer]:
    """Gateway searches only — the ones carrying a concrete layer scope."""
    return [scope for (_q, scope, _lim) in store.searches if scope is not None]


def _searched_layers(store: RecordingStore) -> set[MemoryLayer]:
    return {scope for scope in _scoped_searches(store)}


def _run_sdd(store: RecordingStore, tmp_path: Path, task: str) -> None:
    (tmp_path / "auth.py").write_text("def auth(u, p):\n    return u == p\n", encoding="utf-8")
    runner = HarnessRunner(root=tmp_path, memory_store=store)
    runner.run("sdd", task, BudgetMode.WARN, approved_phases={"apply"})


def test_explore_and_archive_are_excluded_from_the_gateway() -> None:
    """The exclusion set is the symmetric mirror of OC Flow's gather/consolidation."""
    assert _MEMORY_GATEWAY_EXCLUDED_PHASES == frozenset({"explore", "archive"})
    # These two are real phases (present in PHASE_ORDER) — the exclusion is meaningful.
    assert "explore" in PHASE_ORDER
    assert "archive" in PHASE_ORDER


def test_each_middle_phase_recalls_its_read_layers(tmp_path: Path) -> None:
    store = RecordingStore()
    _run_sdd(store, tmp_path, "improve authenticate password hashing")

    # The union of everything the GATEWAY searched (scoped) must cover each MIDDLE
    # phase's read layers — and must NOT be driven by explore/archive.
    expected_read_union: set[MemoryLayer] = set()
    for phase in MIDDLE_PHASES:
        expected_read_union |= set(PHASE_MEMORY_POLICY[phase].read_layers)

    searched = _searched_layers(store)
    missing = expected_read_union - searched
    assert not missing, f"middle phases never recalled these read layers: {missing}"


def test_each_middle_phase_persists_its_write_layers(tmp_path: Path) -> None:
    store = RecordingStore()
    _run_sdd(store, tmp_path, "improve authenticate password hashing")

    expected_write_union: set[MemoryLayer] = set()
    for phase in MIDDLE_PHASES:
        expected_write_union |= set(PHASE_MEMORY_POLICY[phase].write_layers)

    # Gateway writes carry the phase name in structured metadata; the harvester's
    # archive writes do not go through the gateway. We assert the gateway covered
    # every middle write layer.
    gateway_written = {
        rec.layer
        for rec in store.writes
        if isinstance(rec.structured, dict) and rec.structured.get("phase") in MIDDLE_PHASES
    }
    missing = expected_write_union - gateway_written
    assert not missing, f"middle phases never persisted these write layers: {missing}"


def test_gateway_never_recalls_or_persists_for_explore_or_archive(tmp_path: Path) -> None:
    """No gateway write may be tagged explore/archive; those phases own their memory."""
    store = RecordingStore()
    _run_sdd(store, tmp_path, "improve authenticate hashing")

    tagged_phases = {
        rec.structured.get("phase")
        for rec in store.writes
        if isinstance(rec.structured, dict) and rec.structured.get("phase") is not None
    }
    assert "explore" not in tagged_phases, "gateway double-persisted explore (it owns its memory)"
    assert "archive" not in tagged_phases, "gateway double-persisted archive (it owns its memory)"


def test_recall_count_matches_middle_read_layer_cardinality(tmp_path: Path) -> None:
    """The gateway issues one SCOPED search per declared read layer per MIDDLE phase.

    ExplorePhase's own recall and the harvester also hit the shared store, but
    ALWAYS with ``scope=None`` (whole-store sweeps). The gateway is the only
    consumer that searches with a concrete layer scope, so the count of scoped
    searches must equal the sum of ``read_layers`` over the MIDDLE phases —
    explore's read layers are excluded because explore is not driven by the
    gateway.
    """
    store = RecordingStore()
    _run_sdd(store, tmp_path, "improve authenticate hashing")

    scoped = _scoped_searches(store)
    expected_searches = sum(len(PHASE_MEMORY_POLICY[p].read_layers) for p in MIDDLE_PHASES)
    assert len(scoped) == expected_searches, (
        f"expected {expected_searches} scoped searches (sum of read_layers over the "
        f"MIDDLE phases {MIDDLE_PHASES}), got {len(scoped)}"
    )


def test_explore_bespoke_recall_still_runs_exactly_once(tmp_path: Path) -> None:
    """ExplorePhase keeps its ONE unscoped recall; the gateway does not add a second.

    Because explore is excluded from the gateway, the only ``scope=None`` search
    over ``state.task`` in the whole run is ExplorePhase's bespoke fold-into-
    context recall. There must be exactly one such whole-store sweep of the task
    query (no gateway double, no harvester query — the harvester reads run
    artifacts, not the raw task string via ``search``).
    """
    store = RecordingStore()
    task = "improve authenticate password hashing"
    _run_sdd(store, tmp_path, task)

    explore_recalls = [
        (q, scope) for (q, scope, _lim) in store.searches if scope is None and q == task
    ]
    assert len(explore_recalls) == 1, (
        "explore's bespoke recall must issue exactly ONE unscoped search of the task "
        f"(gateway must not double it); got {len(explore_recalls)}: {explore_recalls}"
    )


def test_archive_bespoke_persist_still_occurs(tmp_path: Path) -> None:
    """ArchivePhase's harvester still writes; the gateway does not persist archive.

    A successful sdd run harvests at archive. Those writes are NOT gateway writes
    (no ``phase`` structured tag), proving archive keeps its bespoke persistence
    while being excluded from the gateway.
    """
    store = RecordingStore()
    _run_sdd(store, tmp_path, "improve authenticate hashing")

    non_gateway_writes = [
        rec
        for rec in store.writes
        if not (isinstance(rec.structured, dict) and rec.structured.get("phase"))
    ]
    assert non_gateway_writes, (
        "archive's bespoke harvester persist did not occur (no non-gateway writes seen)"
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
