"""PR-000.4 candidate extractor (SPEC DL-003, reuse backend DL-010)."""

from __future__ import annotations

import types

from opencontext_core.learning import candidate_extractor
from opencontext_core.learning.candidate_extractor import (
    LearningCandidate,
    LearningCandidateKind,
    LearningOutcome,
    extract,
    score_outcome,
)


def _run_result(**kw):
    base = {"run_id": "run-1", "status": "passed", "gates": [], "context_omitted_paths": []}
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_extract_classifies_candidate_with_evidence_and_kind() -> None:
    # DL-003: a run with omitted context paths yields a classified candidate
    # carrying non-empty evidence_refs.
    run = _run_result(context_omitted_paths=["a.py", "b.py", "c.py"])
    candidates = extract(run_result=run)
    assert candidates, "expected at least one candidate"
    weight = [c for c in candidates if c.kind == LearningCandidateKind.context_weight]
    assert weight, "expected a context_weight candidate"
    assert weight[0].evidence_refs  # non-empty evidence
    assert weight[0].run_id == "run-1"
    assert isinstance(weight[0], LearningCandidate)


def test_extract_uses_evolution_engine_propose_from_run(monkeypatch) -> None:
    # DL-010: the proposal backend is EvolutionEngine.propose_from_run, not a
    # second engine re-derived here.
    calls: list[bool] = []
    real = candidate_extractor.EvolutionEngine.propose_from_run

    def spy(self, **kwargs):
        calls.append(True)
        return real(self, **kwargs)

    monkeypatch.setattr(candidate_extractor.EvolutionEngine, "propose_from_run", spy)
    extract(run_result=_run_result(context_omitted_paths=["x.py"]))
    assert calls, "extract did not call EvolutionEngine.propose_from_run"


def test_memory_records_become_promotion_candidates() -> None:
    rec = types.SimpleNamespace(record_id="m1", content="prefer ruff over flake8", confidence=0.7)
    candidates = extract(run_result=_run_result(), harvested=[rec])
    promo = [c for c in candidates if c.kind == LearningCandidateKind.memory_promotion]
    assert promo and promo[0].evidence_refs == ["memory:m1"]


def test_score_outcome_carries_candidate_id_and_metrics() -> None:
    # DL-003 outcome scenario.
    run = _run_result(context_omitted_paths=["a.py"])
    candidate = extract(run_result=run)[0]
    outcome = score_outcome(candidate, run)
    assert isinstance(outcome, LearningOutcome)
    assert outcome.candidate_id == candidate.candidate_id
    assert outcome.success is True
    assert "confidence" in outcome.metrics
