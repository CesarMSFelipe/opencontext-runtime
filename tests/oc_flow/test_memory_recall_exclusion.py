"""Irrelevant memory is excluded from OC Flow recall (MEMORY_CONTRACT rule 4).

MEM-004: irrelevant memory is not used. `_fold_memory_recall` (via
`node_gather_context`) delegates relevance to the stores' search — this pins
the fold level: a run whose stores hold only unrelated records reports
``memory.used == false``, and when relevant and irrelevant observations
coexist, only the relevant one is folded into the envelope/hits.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from opencontext_memory import MemoryStore, mem_save

from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    node_gather_context,
)
from opencontext_core.oc_flow.run_bundle import memory_block

_TASK = "Fix failing auth token expiry test"
_IRRELEVANT = "Quarterly marketing budget spreadsheet totals were reconciled."
_RELEVANT = "The auth token expiry must be validated against the session clock."

#: The two markers `_fold_memory_recall` stamps on genuinely recalled records
#: (the executor's no-seed "memory:task-statement-fallback" item is not recall).
_RECALL_MARKERS = ("memory:score", "memory:observation")


def _recalled(ctx: OCFlowContext) -> list:
    assert ctx.envelope is not None
    return [i for i in ctx.envelope.items if i.why_included.startswith(_RECALL_MARKERS)]


def _ctx(root: Path, store: object | None) -> OCFlowContext:
    artifacts = root / "artifacts" / "oc-flow"
    artifacts.mkdir(parents=True, exist_ok=True)
    (root / "auth.py").write_text("def check_token(token):\n    return token\n", encoding="utf-8")
    return OCFlowContext(
        root=root,
        artifacts_dir=artifacts,
        task=_TASK,
        lane=Lane.FAST,
        profile="balanced",
        executor=DeterministicNodeExecutor(),
        max_attempts=2,
        seed_paths=["auth.py"],
        memory_enabled=True,
        memory_store=store,
    )


def _agent_record(key: str, content: str) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=f"mem-{key}",
        layer=MemoryLayer.SEMANTIC,
        key=key,
        content=content,
        confidence=0.9,
        decay_policy=DecayPolicy(enabled=True),
        created_at=now,
        updated_at=now,
    )


def _save_observation(root: Path, title: str, content: str) -> int:
    db = root / ".storage" / "opencontext" / "memory_v2.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    receipt = mem_save(
        MemoryStore.open(db),
        session_id="s-1",
        project=root.name,
        title=title,
        content=content,
        type="fact",
    )
    return int(receipt.receipt.id)


def test_run_with_only_irrelevant_memory_reports_unused(tmp_path: Path) -> None:
    """MEM-004: a run over stores holding only unrelated records folds nothing."""
    agent_store = LocalMemoryStore(tmp_path / "memory.db")
    agent_store.write(_agent_record("marketing", _IRRELEVANT))
    _save_observation(tmp_path, "Marketing note", _IRRELEVANT)

    ctx = _ctx(tmp_path, agent_store)
    node_gather_context(ctx)

    assert _recalled(ctx) == []
    assert ctx.memory_hits == []
    assert memory_block(ctx.memory_hits)["used"] is False


def test_irrelevant_observation_excluded_while_relevant_is_folded(tmp_path: Path) -> None:
    """MEM-004: with mixed observations only the relevant one reaches hits."""
    relevant_id = _save_observation(tmp_path, "Auth rule", _RELEVANT)
    irrelevant_id = _save_observation(tmp_path, "Marketing note", _IRRELEVANT)

    ctx = _ctx(tmp_path, LocalMemoryStore(tmp_path / "memory.db"))
    node_gather_context(ctx)

    hit_ids = {h["id"] for h in ctx.memory_hits}
    assert str(relevant_id) in hit_ids
    assert str(irrelevant_id) not in hit_ids
    summaries = [i.summary for i in _recalled(ctx)]
    assert any("auth token expiry" in s for s in summaries)
    assert not any("marketing" in s.lower() for s in summaries)
    assert memory_block(ctx.memory_hits)["used"] is True
