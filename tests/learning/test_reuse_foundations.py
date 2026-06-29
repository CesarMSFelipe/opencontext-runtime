"""PR-000.4 reuse-not-duplicate assertions (SPEC DL-010..DL-013)."""

from __future__ import annotations

import inspect


def test_loop_reuses_existing_foundations() -> None:
    # DL-010..012: the loop wires the existing engine/store/collector — it does
    # not redefine them.
    import opencontext_core.learning.loop as loop_mod

    source = inspect.getsource(loop_mod)
    assert "EvolutionEngine" in source
    assert "EvolutionStore" in source
    assert "FeedbackCollector" in source
    assert "RuntimeFeedback" in source
    # No parallel proposal store / collector is defined in the loop.
    assert "class EvolutionStore" not in source
    assert "class FeedbackCollector" not in source


def test_extractor_backend_is_evolution_engine() -> None:
    # DL-010: the extractor imports and uses EvolutionEngine.propose_from_run.
    import opencontext_core.learning.candidate_extractor as extractor_mod

    source = inspect.getsource(extractor_mod)
    assert "from opencontext_core.learning.evolution_engine import EvolutionEngine" in source
    assert "propose_from_run" in source


def test_improvement_proposal_extends_evolution_proposal() -> None:
    # DL-005: ImprovementProposal is (or extends) EvolutionProposal.
    from opencontext_core.learning.evolution import EvolutionProposal, ImprovementProposal

    assert ImprovementProposal is EvolutionProposal or issubclass(
        ImprovementProposal, EvolutionProposal
    )


def test_replay_ledger_reused_not_redefined() -> None:
    # DL-013: the RunEvent / RuntimeTrace replay ledger exists and is the single
    # replay foundation; the Decision Log references trace ids, never copies events.
    from opencontext_core.models.trace import RunEvent, RuntimeTrace

    assert "event_ledger" in RuntimeTrace.model_fields
    assert RunEvent is not None

    import opencontext_core.runtime.decision_log as dl_mod

    source = inspect.getsource(dl_mod)
    assert "class RunEvent" not in source  # no parallel replay ledger
    assert "trace_id" in source  # references the trace ledger by id


def test_benchmark_evidence_ref_on_base_model() -> None:
    # DL-009/DL-011: the honesty field lives on the persisted EvolutionProposal so
    # EvolutionStore round-trips it (no subclass-extra-field breakage).
    from opencontext_core.learning.evolution import EvolutionProposal

    assert "benchmark_evidence_ref" in EvolutionProposal.model_fields
