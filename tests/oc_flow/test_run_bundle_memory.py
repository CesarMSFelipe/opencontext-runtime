"""OC Flow run.json memory block: hits recorded per MEMORY_CONTRACT rule 4 (AC-018)."""

from __future__ import annotations

from opencontext_core.oc_flow.run_bundle import memory_block


def test_memory_block_with_hits_reports_used() -> None:
    hits = [{"id": "7", "type": "project_context", "score": 0.5, "used_for": "context_pack"}]
    block = memory_block(hits)
    assert block == {
        "used": True,
        "hits": hits,
        "new_candidates": 0,
        "requires_approval": False,
    }


def test_memory_block_without_hits_reports_unused() -> None:
    assert memory_block([]) == {
        "used": False,
        "hits": [],
        "new_candidates": 0,
        "requires_approval": False,
    }


def test_memory_block_copies_the_hits_list() -> None:
    hits: list[dict] = [{"id": "1", "type": "fact", "score": 1.0, "used_for": "context_pack"}]
    block = memory_block(hits)
    hits.append({"id": "2", "type": "fact", "score": 1.0, "used_for": "context_pack"})
    assert len(block["hits"]) == 1
