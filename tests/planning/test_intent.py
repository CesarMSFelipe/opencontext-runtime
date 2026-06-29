"""Tests for IntentRecord + parse_intent (SPEC MP-002, MP-003)."""

from __future__ import annotations

from opencontext_core.planning.intent import (
    KNOWN_ARCHITECTURE_DOCS,
    IntentRecord,
    map_to_docs,
    parse_intent,
)


def test_parse_returns_record_with_matching_raw_text_and_goal() -> None:
    raw = "Build a governed runtime. It must turn intent into a program of PRs."
    record = parse_intent(raw)

    assert isinstance(record, IntentRecord)
    assert record.raw_text == raw
    assert record.goal  # non-empty
    assert record.goal == "Build a governed runtime."


def test_schema_version_is_intent_v1() -> None:
    assert parse_intent("anything").schema_version == "opencontext.intent.v1"


def test_referenced_docs_non_empty_for_roadmap_backlog_intent() -> None:
    record = parse_intent("Map the roadmap and backlog onto the architecture.")
    assert record.referenced_docs  # non-empty
    assert all(doc in KNOWN_ARCHITECTURE_DOCS for doc in record.referenced_docs)
    assert "16" in record.referenced_docs  # roadmap
    assert "43" in record.referenced_docs  # backlog


def test_map_to_docs_only_returns_known_doc_ids() -> None:
    docs = map_to_docs("validation convergence matrix and release sequencing gates")
    assert docs
    assert all(doc in KNOWN_ARCHITECTURE_DOCS for doc in docs)


def test_map_to_docs_falls_back_to_system_architecture() -> None:
    # No keyword matches -> falls back to doc 01 so every intent stays traceable.
    assert map_to_docs("zzz qqq nothing relevant here") == ["01"]


def test_outcomes_and_constraints_extracted() -> None:
    record = parse_intent(
        "Plan the program so that we deliver coverage. The plan must be deterministic."
    )
    assert any("deliver" in o.lower() for o in record.outcomes)
    assert any("must" in c.lower() for c in record.constraints)
