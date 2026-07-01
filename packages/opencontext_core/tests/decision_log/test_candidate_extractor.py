"""NoCoT candidate extraction (PR-000.4 / SPEC DL-002/003).

Acceptance: decision-bearing text yields structured LearningCandidate entries
with stable ids; empty input yields nothing; entries are redacted through
the NoCoT redaction layer when present.
"""
from __future__ import annotations

from opencontext_core.learning.v2.candidate_extractor import (
    LearningCandidate,
    extract_learning_candidates,
)


def test_extract_from_decision_text_yields_entries_with_required_fields():
    text = (
        "We decided to use pytest with PYTHONPATH=packages/opencontext_core. "
        "Decision: stage changes by layer."
    )
    candidates = extract_learning_candidates(text, run_id="run-1")

    assert len(candidates) >= 1
    first = candidates[0]
    assert isinstance(first, LearningCandidate)
    assert first.run_id == "run-1"
    assert first.candidate_id  # non-empty stable id
    assert first.kind  # non-empty classification
    assert first.summary  # non-empty redacted decision text


def test_extract_empty_text_yields_no_candidates():
    assert extract_learning_candidates("", run_id="run-empty") == []


def test_extract_reuses_existing_no_cot_patterns():
    """Patterns covered: decided|chose|selected|went with, decision: prefix."""
    text = "Chose Pydantic v2 for models. Went with SQLite for L2 store."
    candidates = extract_learning_candidates(text, run_id="run-2")
    kinds = [c.kind for c in candidates]
    # At least one candidate per non-empty pattern match
    assert any(k == "decision_pattern" for k in kinds)


def test_extracted_summary_is_no_cot_safe():
    """NoCoT invariant: summaries pass through the redactor — non-empty and bounded."""
    text = (
        "Decision: Use pytest with PYTHONPATH=packages/opencontext_core; "
        "this avoids sys.path mutation at runtime."
    )
    candidates = extract_learning_candidates(text, run_id="run-cot")
    assert candidates, "Decision: prefix must match the extractor"
    for c in candidates:
        assert c.summary  # non-empty
        assert len(c.summary) <= 280  # bounded per DL-007 cap
