"""PR-000.4 no-chain-of-thought guard (SPEC DL-007, anti-regression).

CRITICAL INVARIANT: the Decision Log and Learning Loop must never persist model
chain-of-thought. Every persisted rationale/summary is redacted to a durable
summary first.
"""

from __future__ import annotations

import types

from opencontext_core.learning.candidate_extractor import LearningCandidateKind, extract
from opencontext_core.learning.evolution import EvolutionProposal
from opencontext_core.learning.promotion import harden_proposal
from opencontext_core.policy.memory_content import forbidden_memory_content
from opencontext_core.runtime.decision_log import (
    DecisionRecorder,
    SelectionKind,
    redact_chain_of_thought,
)

_COT = (
    "<thinking>Let me think step by step. First, I'll inspect the budget. "
    "reasoning: the limit is too low.</thinking> Decision: raise the budget to 8000."
)


def test_redact_reduces_cot_to_durable_summary() -> None:
    redacted = redact_chain_of_thought(_COT)
    assert forbidden_memory_content(redacted) is None
    assert "<thinking>" not in redacted
    assert "step by step" not in redacted
    # The durable decision survives.
    assert "8000" in redacted


def test_durable_text_passes_through_unchanged() -> None:
    durable = "Raised the token budget to 8000 after repeated omissions."
    assert redact_chain_of_thought(durable) == durable


def test_decision_log_entry_rationale_is_redacted() -> None:
    recorder = DecisionRecorder()
    entry = recorder.record_selection(
        decision_kind=SelectionKind.profile, selected="fast", rationale=_COT
    )
    assert forbidden_memory_content(entry.rationale) is None
    assert "<thinking>" not in entry.rationale


def test_candidate_summary_is_redacted() -> None:
    rec = types.SimpleNamespace(record_id="m1", content=_COT, confidence=0.6)
    run = types.SimpleNamespace(run_id="r1", status="passed", gates=[], context_omitted_paths=[])
    candidates = extract(run_result=run, harvested=[rec])
    promo = [c for c in candidates if c.kind == LearningCandidateKind.memory_promotion]
    assert promo
    assert forbidden_memory_content(promo[0].summary) is None


def test_harden_proposal_redacts_title_and_rationale() -> None:
    proposal = EvolutionProposal(
        proposal_id="p1", kind="skill_candidate", title=_COT, rationale=_COT
    )
    hardened = harden_proposal(proposal)
    assert forbidden_memory_content(hardened.title) is None
    assert forbidden_memory_content(hardened.rationale) is None
