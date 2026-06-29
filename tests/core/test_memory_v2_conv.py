"""PR-009 Phase CONV: quality score, stale audit, typed conflicts, profile, learning seam."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from opencontext_core.memory.consolidation import memory_quality_score
from opencontext_core.memory.contradictions import ContradictionDetector
from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.memory.learning_seam import build_learning_candidates, feed_memory_outcome
from opencontext_core.memory.retrieval import apply_profile
from opencontext_core.memory.stale_audit import stale_audit
from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryRecord,
    MemoryStatus,
)
from opencontext_core.models.evidence import EvidenceRef
from opencontext_core.models.memory import MemoryConflict, MemoryQuery


def _rec(
    rid: str,
    *,
    content: str = "a durable belief about the system",
    confidence: float = 0.9,
    refs: int = 0,
    revisions: int = 0,
    age_days: int = 0,
    contradicted: bool = False,
    layer: MemoryLayer = MemoryLayer.SEMANTIC,
) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    ts = now - timedelta(days=age_days)
    return MemoryRecord(
        id=rid,
        layer=layer,
        key=f"k:{rid}",
        content=content,
        confidence=confidence,
        source_refs=[
            EvidenceRef(source=f"e{i}.py", source_type="file", confidence=0.9) for i in range(refs)
        ],
        decay_policy=DecayPolicy(enabled=False),
        created_at=ts,
        updated_at=ts,
        revision_count=revisions,
        contradicted_by=["other"] if contradicted else [],
    )


# -- CONV.2 quality score ---------------------------------------------------


def test_quality_score_low_for_no_evidence_never_read() -> None:
    poor = _rec("poor", confidence=0.3, refs=0, revisions=0, age_days=200)
    rich = _rec("rich", confidence=0.9, refs=2, revisions=3, age_days=1)
    assert memory_quality_score(poor) < 0.3
    assert memory_quality_score(rich) > memory_quality_score(poor)


# -- CONV.3 stale audit -----------------------------------------------------


def test_stale_audit_flags_contradicted_low_confidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalMemoryStore(Path(tmp) / "mem.db")
        store.write(_rec("stale1", confidence=0.2, contradicted=True))
        store.write(_rec("fresh1", confidence=0.95, refs=2))
        findings = stale_audit(store)
        flagged = {f.record.id: f for f in findings}
        assert "stale1" in flagged
        assert flagged["stale1"].record.status == MemoryStatus.STALE
        assert "fresh1" not in flagged


# -- CONV.4 typed conflict reports ------------------------------------------


def test_detect_returns_typed_conflicts_and_id_shim() -> None:
    detector = ContradictionDetector()
    new = _rec("new", content="auth uses bearer tokens", confidence=0.95)
    new = new.model_copy(update={"key": "auth:flow"})
    old = _rec("old", content="auth uses cookie sessions", confidence=0.5)
    old = old.model_copy(update={"key": "auth:flow"})
    conflicts = detector.detect(new, [old])
    assert conflicts and isinstance(conflicts[0], MemoryConflict)
    assert conflicts[0].record_id == "old"
    assert detector.detect_ids(new, [old]) == ["old"]


# -- CONV.5 profile-aware retrieval -----------------------------------------


def test_profile_tunes_budget_and_min_confidence() -> None:
    query = MemoryQuery(task="t", max_records=8, max_tokens=2000, min_confidence=0.0)
    low = apply_profile(query, "low-cost")
    assert low.max_records == 4
    assert low.max_tokens == 1000
    assert low.min_confidence >= 0.1
    # Unknown/empty profile leaves the query unchanged.
    assert apply_profile(query, "") == query


# -- CONV.1 learning-loop seam ----------------------------------------------


def test_learning_seam_builds_candidates_and_is_non_blocking() -> None:
    records = [_rec("f1", layer=MemoryLayer.FAILURE), _rec("s1", layer=MemoryLayer.SEMANTIC)]
    candidates = build_learning_candidates(records, task="fix bug")
    assert {c.record_id for c in candidates} == {"f1", "s1"}
    assert any(c.is_failure for c in candidates)
    # No orchestrator wired: returns candidates without raising.
    assert feed_memory_outcome(None, task="fix bug", records=records) == candidates


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
