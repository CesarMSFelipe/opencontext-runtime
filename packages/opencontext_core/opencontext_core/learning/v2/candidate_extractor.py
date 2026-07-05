"""NoCoT learning-candidate extraction (PR-000.4 / SPEC DL-003).

Advisory L8 module — wraps :class:`opencontext_core.decision_log.recorder.NoCoTExtractor`
to surface run text as durable ``LearningCandidate`` records (one per matched
decision pattern). Every durable text field is passed through
:func:`redact_chain_of_thought` before it lands in the model (DL-007).

This module is propose-only: it never writes to memory, the KG, or any
Brain-adjacent port. Promotion is the gated responsibility of
:mod:`opencontext_core.learning.v2.promotion_gate`; human approval is the
gated responsibility of :mod:`opencontext_core.learning.v2.improvement_proposal`.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum
from opencontext_core.decision_log.recorder import DecisionLogEntry, NoCoTExtractor
from opencontext_core.runtime.decision_log import redact_chain_of_thought

# Stable candidate-id derivation (sha256 prefix is enough; deterministic by construction).
_MAX_SUMMARY_CHARS = 280


class LearningCandidateKind(StrEnum):
    """How a learning candidate is classified (DL-003).

    v2 ships only the kind it actually produces from NoCoT extraction.
    Add kinds only when their source appears.
    """

    decision_pattern = "decision_pattern"


class LearningCandidate(BaseModel):
    """One structured, evidence-backed learning candidate (durable, no CoT)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.learning_candidate.v2"
    candidate_id: str
    run_id: str
    kind: LearningCandidateKind
    summary: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = 0.5


def _candidate_id(run_id: str, summary: str) -> str:
    digest = hashlib.sha256(f"{run_id}:{summary}".encode()).hexdigest()[:16]
    return f"cand-{digest}"


def _to_candidate(entry: DecisionLogEntry, run_id: str) -> LearningCandidate:
    summary = redact_chain_of_thought(entry.decision)[:_MAX_SUMMARY_CHARS]
    return LearningCandidate(
        candidate_id=_candidate_id(run_id, summary or entry.id),
        run_id=run_id,
        kind=LearningCandidateKind.decision_pattern,
        summary=summary,
        evidence_refs=[entry.id],
        confidence=float(entry.confidence or 0.5),
    )


def extract_learning_candidates(
    text: str, run_id: str, *, kind: str = "decision"
) -> list[LearningCandidate]:
    """Run the NoCoT extractor over *text* and return durable candidates.

    Empty input yields an empty list (no spurious candidates).
    """
    if not text or not text.strip():
        return []
    extractor = NoCoTExtractor()
    entries = extractor.extract(text, kind=kind)
    seen: set[str] = set()
    out: list[LearningCandidate] = []
    for e in entries:
        cand = _to_candidate(e, run_id)
        if cand.candidate_id in seen:
            continue
        seen.add(cand.candidate_id)
        out.append(cand)
    return out


__all__ = [
    "LearningCandidate",
    "LearningCandidateKind",
    "extract_learning_candidates",
]
