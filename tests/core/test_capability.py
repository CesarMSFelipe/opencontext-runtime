"""Tests for capability scoring.

``score_matrix`` derives ``kg_grounding`` from real evidence on the pack
(``included_sources``), reads the rest from ``run_metadata``, and HARD-forces the two
KG-exclusive capabilities (``kg_grounding``, ``impact_consulted``) to False for the
control arms (GENTLE/SIN) — but credits their genuine capabilities (memory, spec,
artifact chain, TDD, portability) honestly from metadata.
"""

from __future__ import annotations

from dataclasses import dataclass

from opencontext_core.evaluation.capability import score_matrix
from opencontext_core.evaluation.multi_arm import CapabilityMatrix


@dataclass
class _FakePack:
    """Stand-in pack carrying only the attribute score_matrix inspects."""

    included_sources: list[str]


_FULL_METADATA = {
    "portability": True,
    "tdd_gate_passed": True,
    "impact_consulted": True,
    "memory_used": True,
    "spec_artifact": True,
    "artifact_chain": True,
    "correctness": True,
}


class TestKgGroundingFromPack:
    def test_oc_arm_with_included_sources_is_grounded(self) -> None:
        pack = _FakePack(included_sources=["src/auth.py", "src/db.py"])
        matrix = score_matrix("OC-SURGICAL", pack, run_metadata=_FULL_METADATA)
        assert matrix.kg_grounding is True
        # Non-control arm keeps its metadata-reported capabilities.
        assert matrix.impact_consulted is True
        assert matrix.tdd_gate is True
        assert matrix.memory_used is True
        assert matrix.spec_artifact is True
        assert matrix.artifact_chain is True
        assert matrix.correctness is True

    def test_oc_arm_without_included_sources_is_not_grounded(self) -> None:
        pack = _FakePack(included_sources=[])
        matrix = score_matrix("OC-BROAD", pack, run_metadata=_FULL_METADATA)
        assert matrix.kg_grounding is False

    def test_missing_attribute_defaults_to_not_grounded(self) -> None:
        matrix = score_matrix("OC-SURGICAL", object(), run_metadata=_FULL_METADATA)
        assert matrix.kg_grounding is False


class TestControlArmsLackOnlyKgCapabilities:
    def test_gentle_denied_kg_and_impact_but_credited_real_capabilities(self) -> None:
        # The two KG-exclusive capabilities are denied no matter what metadata claims —
        # GENTLE greps, it has no knowledge graph.
        pack = _FakePack(included_sources=["src/auth.py"])
        matrix = score_matrix("GENTLE-SIM", pack, run_metadata=_FULL_METADATA)
        assert matrix.kg_grounding is False
        assert matrix.impact_consulted is False
        # But a real SDD system IS credited its genuine capabilities (honest, not a
        # strawman): memory (Engram), spec/artifact chain, TDD gate, portability.
        assert matrix.memory_used is True
        assert matrix.spec_artifact is True
        assert matrix.artifact_chain is True
        assert matrix.tdd_gate is True
        assert matrix.portability is True
        assert matrix.correctness is True

    def test_sin_metadata_controls_non_kg_capabilities(self) -> None:
        # A bare grep+read agent reports no SDD capabilities; only the two KG fields are
        # forced. The caller passes honest per-arm metadata for the rest.
        pack = _FakePack(included_sources=["src/auth.py"])
        bare = {"portability": True, "correctness": False}
        matrix = score_matrix("REALISTIC-SIN", pack, run_metadata=bare)
        assert matrix.kg_grounding is False
        assert matrix.impact_consulted is False
        assert matrix.memory_used is False
        assert matrix.spec_artifact is False
        assert matrix.artifact_chain is False
        assert matrix.portability is True

    def test_control_arms_retain_portability_and_correctness(self) -> None:
        pack = _FakePack(included_sources=[])
        matrix = score_matrix("GENTLE-SIM", pack, run_metadata=_FULL_METADATA)
        assert isinstance(matrix, CapabilityMatrix)
        assert matrix.portability is True
        assert matrix.correctness is True
