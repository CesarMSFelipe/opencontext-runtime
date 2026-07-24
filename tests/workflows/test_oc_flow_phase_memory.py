"""OC Flow's memory-blind middle nodes honor PHASE_MEMORY_POLICY via the gateway.

Sub-PR 2: the middle nodes (``plan``, ``mutate``, ``local_inspection``) were
memory-blind — no recall/persist per ``phase_policy``. The runner now drives the
SAME ``PhaseMemoryGateway`` for a MAPPED node (``OC_FLOW_NODE_TO_PHASE``): a
scoped recall over the mapped phase's ``read_layers`` before the handler and a
persist over its ``write_layers`` after — WITHOUT touching OC Flow's existing
working memory at ``gather_context`` / ``consolidation`` (those keep their own
``_fold_memory_recall`` / harvest and must NOT be double-searched/persisted).

Discriminator (mirrors the SDD harness enforcement test): the PhaseMemoryGateway
is the ONLY consumer that searches with a concrete ``scope=<layer>``; OC Flow's
own ``_fold_memory_recall`` and the harvester ALWAYS search with ``scope=None``.
So a "scoped" search (scope is not None) is unambiguous proof the gateway ran.

The store is injected via ``OCFlowRunner(..., memory_store=<recording fake>)``;
the fake implements ONLY the real port surface (``search`` + ``write``).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opencontext_core.agents.executor import ApplyEdit, ApplyOperation
from opencontext_core.memory.phase_policy import PHASE_MEMORY_POLICY
from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryRecord,
)
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import OC_FLOW_NODE_TO_PHASE
from opencontext_core.oc_flow.runner import OCFlowRunner

# A real surgical edit so the run walks plan -> mutate -> local_inspection with a
# genuine mutation (the deterministic executor applies requested_edits).
_EDIT = ApplyEdit(
    path="calc.py",
    operation=ApplyOperation.REPLACE_RANGE,
    start_line=2,
    end_line=2,
    content="    return a + b",
    reason="fix",
    requirement_refs=["sum"],
)
_TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


@dataclass
class RecordingStore:
    """Recording fake over the real AgentMemoryStore port surface.

    Records every ``search()``/``write()`` — including the ``scope`` — so a test
    can attribute scoped (gateway) searches vs scope=None (OC Flow's own) sweeps.
    """

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


def _project(tmp_path: Path) -> None:
    """A red-then-fixed calc project so a real mutation flows through the graph."""
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "test_calc.py").write_text(_TEST, encoding="utf-8")


def _run(tmp_path: Path, store: RecordingStore) -> Any:
    return OCFlowRunner(root=tmp_path, memory_store=store).run(
        "fix failing add test",
        lane=Lane.FAST,
        requested_edits=[_EDIT],
        test_command=[sys.executable, "-m", "pytest", "-q", "test_calc.py"],
    )


def _scoped_writes(store: RecordingStore) -> list[MemoryRecord]:
    """Records written by the gateway carry structured['phase']; OC Flow's own do not."""
    return [w for w in store.writes if isinstance(w.structured, dict) and "phase" in w.structured]


# ---------------------------------------------------------------------------
# The map only covers the memory-blind middle nodes.
# ---------------------------------------------------------------------------


def test_node_to_phase_map_covers_only_blind_middle_nodes() -> None:
    """plan->propose, mutate->apply, local_inspection->verify; gather/consolidation excluded."""
    assert OC_FLOW_NODE_TO_PHASE["plan"] == "propose"
    assert OC_FLOW_NODE_TO_PHASE["mutate"] == "apply"
    assert OC_FLOW_NODE_TO_PHASE["local_inspection"] == "verify"
    # The nodes that ALREADY own memory must never be mapped (would double up).
    assert "gather_context" not in OC_FLOW_NODE_TO_PHASE
    assert "consolidation" not in OC_FLOW_NODE_TO_PHASE
    # Every mapped phase must be a real phase_policy phase.
    for phase in OC_FLOW_NODE_TO_PHASE.values():
        assert phase in PHASE_MEMORY_POLICY


# ---------------------------------------------------------------------------
# A mapped middle node persists/recalls EXACTLY its phase's layers via the gateway.
# ---------------------------------------------------------------------------


def test_oc_flow_middle_node_honors_phase_policy(tmp_path: Path) -> None:
    """mutate persists apply's write_layers; plan recalls propose's read_layers — exactly those."""
    _project(tmp_path)
    store = RecordingStore()
    _run(tmp_path, store)

    # -- persist: the ONLY scoped writes come from the mapped nodes, and mutate
    #    (mapped to apply) must land EXACTLY apply's write_layers (EPISODIC+FAILURE).
    apply_writes = [w for w in _scoped_writes(store) if w.structured.get("phase") == "apply"]
    assert apply_writes, "mutate node did not persist via the gateway to the apply phase"
    apply_layers = {w.layer for w in apply_writes}
    assert (
        apply_layers
        == set(PHASE_MEMORY_POLICY["apply"].write_layers)
        == {
            MemoryLayer.EPISODIC,
            MemoryLayer.FAILURE,
        }
    )

    # -- recall: the gateway is the ONLY consumer issuing scoped searches. The
    #    scoped searches for the propose phase (plan node) must equal propose's
    #    read_layers (SEMANTIC+WORKING) — exactly those, nothing else.
    scoped = [(q, s, lim) for (q, s, lim) in store.searches if s is not None]
    assert scoped, "no scoped gateway searches were issued for the middle nodes"
    propose_layers = set(PHASE_MEMORY_POLICY["propose"].read_layers)
    # Every scoped search layer must belong to some mapped phase's read_layers
    # (never a layer outside the policy of a mapped node).
    allowed = set()
    for phase in OC_FLOW_NODE_TO_PHASE.values():
        allowed |= set(PHASE_MEMORY_POLICY[phase].read_layers)
    assert {s for (_q, s, _l) in scoped} <= allowed
    # propose's declared read layers were each searched at least once (plan recall).
    assert propose_layers <= {s for (_q, s, _l) in scoped}
    # verify's read layers too (local_inspection recall).
    assert set(PHASE_MEMORY_POLICY["verify"].read_layers) <= {s for (_q, s, _l) in scoped}


def test_oc_flow_scoped_search_count_matches_mapped_read_layers(tmp_path: Path) -> None:
    """Exactly one scoped search per mapped node's declared read layer — no extras.

    A single happy-path run visits each mapped node once (plan, mutate,
    local_inspection), so the count of scoped searches must equal the sum of the
    mapped phases' read_layers. Anything more means a node was double-recalled.
    """
    _project(tmp_path)
    store = RecordingStore()
    _run(tmp_path, store)

    scoped = [s for (_q, s, _l) in store.searches if s is not None]
    expected = sum(len(PHASE_MEMORY_POLICY[p].read_layers) for p in OC_FLOW_NODE_TO_PHASE.values())
    assert len(scoped) == expected, (
        f"expected {expected} scoped searches (sum of mapped read_layers), got {len(scoped)}"
    )


# ---------------------------------------------------------------------------
# gather_context and consolidation keep their OWN memory — never doubled.
# ---------------------------------------------------------------------------


def test_oc_flow_gather_and_consolidation_not_doubled(tmp_path: Path) -> None:
    """No scoped gateway recall/persist for gather_context or consolidation.

    Their existing memory (_fold_memory_recall / harvest) is the ONLY memory
    there; the gateway must be a no-op for their (unmapped) node names, so no
    scoped search and no phase-tagged write ever carries their phase.
    """
    _project(tmp_path)
    store = RecordingStore()
    _run(tmp_path, store)

    # gather_context maps to no phase; explore/archive are its would-be phases but
    # must NEVER appear as a scoped write phase (the gateway was not invoked there).
    scoped_write_phases = {w.structured.get("phase") for w in _scoped_writes(store)}
    assert scoped_write_phases <= set(OC_FLOW_NODE_TO_PHASE.values()), (
        f"a non-mapped node persisted via the gateway: {scoped_write_phases}"
    )
    # And specifically the middle-node phases only — no explore/archive/spec/etc.
    assert "explore" not in scoped_write_phases
    assert "archive" not in scoped_write_phases

    # OC Flow's own memory still ran: gather_context's _fold_memory_recall issued
    # its scope=None sweep (the whole-store search), proving it was NOT replaced.
    unscoped = [s for (_q, s, _l) in store.searches if s is None]
    assert unscoped, "gather_context's own (scope=None) memory recall did not run"


# ---------------------------------------------------------------------------
# Regression: the existing _fold_memory_recall path is unchanged.
# ---------------------------------------------------------------------------


def test_oc_flow_existing_recall_still_works(tmp_path: Path) -> None:
    """_fold_memory_recall behavior unchanged: memory_hits populated + run.json memory block."""
    import json

    _project(tmp_path)
    # A canned record so gather_context's fold produces a real memory hit.
    store = RecordingStore(canned="prior run: add() had an off-by-one in the operator")
    result = _run(tmp_path, store)

    assert result.artifacts_dir is not None
    # The run.json memory block is still written with the folded hit.
    run_json = json.loads((result.artifacts_dir.parent.parent / "run.json").read_text())
    memory_block = run_json["memory"]
    assert memory_block["used"] is True
    assert memory_block["hits"], "the folded memory hit is missing from run.json"
    # The folded hit came from gather_context's own recall (used_for=context_pack),
    # NOT from the gateway (which never records run.json hits).
    assert any(h.get("used_for") == "context_pack" for h in memory_block["hits"])
