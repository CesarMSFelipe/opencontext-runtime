"""OpenContext learning layer v2 (PR-000.4 / SPEC DL-003 / DL-004 / DL-009).

Advisory L8 — proposes only, never mutates a target. The three exported
modules combine to:
  * :mod:`candidate_extractor` — pull learning candidates from run text (NoCoT)
  * :mod:`promotion_gate` — gate promotion to memory (quality + benchmark evidence)
  * :mod:`improvement_proposal` — write-only proposals that require human approval

The package deliberately exposes NO write paths into the KG, memory, or
Brain-adjacent layers; promotion is the destination harness's job.
"""

from __future__ import annotations

from opencontext_core.learning.v2.candidate_extractor import (
    LearningCandidate,
    LearningCandidateKind,
    extract_learning_candidates,
)
from opencontext_core.learning.v2.improvement_proposal import (
    ApprovalRequired,
    ImprovementProposal,
)
from opencontext_core.learning.v2.promotion_gate import (
    MemoryPromotionRejected,
    PromotionGate,
    PromotionResult,
)

__all__ = [
    "ApprovalRequired",
    "ImprovementProposal",
    "LearningCandidate",
    "LearningCandidateKind",
    "MemoryPromotionRejected",
    "PromotionGate",
    "PromotionResult",
    "extract_learning_candidates",
]
