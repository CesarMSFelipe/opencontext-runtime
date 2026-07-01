"""Quick tests for PR-000.3/009/000.4 core modules."""

from __future__ import annotations


def test_cache_leaf_get_set() -> None:
    from opencontext_core.cache.v2 import SemanticCache
    c = SemanticCache()
    c.set("k", 42)
    assert c.get("k") == 42
    assert c.get("missing") is None

def test_cache_invalidate() -> None:
    from opencontext_core.cache.v2 import SemanticCache
    c = SemanticCache()
    c.set("a", 1)
    c.set("b", 2)
    removed = c.apply_delta({"a"})
    assert removed == 1
    assert c.get("a") is None
    assert c.get("b") == 2

def test_memory_harness_conflict_detection() -> None:
    from opencontext_core.memory.v2.harness import MemoryHarnessV2
    m = MemoryHarnessV2()
    records = [
        {"id": 1, "topic_key": "auth", "type": "decision", "content": "use jwt"},
        {"id": 2, "topic_key": "auth", "type": "decision", "content": "use oauth"},
    ]
    conflicts = m.detect_conflicts(records)
    assert len(conflicts) == 1

def test_decision_recorder() -> None:
    from opencontext_core.decision_log.recorder import DecisionRecorder, DecisionLogEntry
    d = DecisionRecorder()
    e = DecisionLogEntry(id="dec-1", kind="architecture", decision="use hexagonal")
    d.record(e)
    assert len(d.list_by_kind("architecture")) == 1
    assert d.promote("dec-1") is True
