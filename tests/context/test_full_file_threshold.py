"""MET-TOKENS: wire `retrieval.full_file_threshold` into pack compilation.

DOC2 §29.2 requires >= 80% irrelevant-file exclusion on the large fixture, but
`retrieval.full_file_threshold` ("Relevance threshold below which a whole file
is not loaded", default 0.8) was documented config consumed NOWHERE: the packer
happily filled leftover budget with 0.33-scoring distractor files. These tests
pin the wiring in :class:`ContextCompiler`:

* when symbol evidence exists (symbol-first retrieval did its job), whole-file
  items scoring below the threshold are omitted with a traceable reason;
* protected items are never threshold-omitted;
* without symbol evidence the threshold is inert (whole files are the only
  representation available — dropping them would empty the pack).
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.context.compiler import ContextCompiler
from opencontext_core.retrieval.contracts import (
    EvidenceItem,
    EvidencePlan,
    EvidenceRequest,
    FreshnessStatus,
    RetrievalSurface,
    TrustDecision,
)


def _evidence(
    item_id: str,
    *,
    source: str,
    source_type: str,
    confidence: float,
    protected: bool = False,
    tokens: int = 5,
) -> EvidenceItem:
    return EvidenceItem(
        id=item_id,
        content=f"content of {item_id}",
        source=source,
        source_type=source_type,
        provenance={"source": source, "source_type": source_type},
        confidence=confidence,
        freshness=FreshnessStatus.CURRENT,
        surface=RetrievalSurface.RUNTIME,
        tokens=tokens,
        protected=protected,
    )


def _plan(items: list[EvidenceItem], tmp_path: Path) -> EvidencePlan:
    return EvidencePlan(
        request=EvidenceRequest(
            query="fix the calculator bug",
            root=tmp_path,
            surface=RetrievalSurface.RUNTIME,
            max_tokens=500,
            risk_level="normal",
        ),
        evidence=items,
        fallback_actions=[],
        trust_decision=TrustDecision(status="sufficient", reason="fixture"),
        trace_id="trace-fixture",
        source_surfaces=[RetrievalSurface.RUNTIME],
    )


def _compile(items: list[EvidenceItem], tmp_path: Path, threshold: float | None):
    return ContextCompiler().compile(_plan(items, tmp_path), full_file_threshold=threshold)


def test_low_scoring_whole_files_are_omitted_when_symbols_exist(tmp_path: Path) -> None:
    """MET-TOKENS: with symbol evidence in the plan, whole files scoring below
    full_file_threshold are excluded with a traceable omission reason."""
    items = [
        _evidence(
            "graph:calc.py:4:multiply",
            source="calc.py:4",
            source_type="graph_symbol",
            confidence=0.9,
        ),
        _evidence("file:calc.py", source="calc.py", source_type="file", confidence=0.55),
        _evidence(
            "file:distractor.py", source="distractor.py", source_type="file", confidence=0.33
        ),
    ]
    pack = _compile(items, tmp_path, threshold=0.8)

    included_ids = [item.id for item in pack.included]
    assert included_ids == ["graph:calc.py:4:multiply"]
    omission_reasons = {o.item_id: o.reason for o in pack.omissions}
    assert omission_reasons.get("file:calc.py") == "below_full_file_threshold"
    assert omission_reasons.get("file:distractor.py") == "below_full_file_threshold"


def test_whole_files_at_or_above_threshold_are_kept(tmp_path: Path) -> None:
    """MET-TOKENS: a whole file whose relevance meets the threshold is loaded."""
    items = [
        _evidence(
            "graph:calc.py:4:multiply",
            source="calc.py:4",
            source_type="graph_symbol",
            confidence=0.9,
        ),
        _evidence("file:calc.py", source="calc.py", source_type="file", confidence=0.85),
    ]
    pack = _compile(items, tmp_path, threshold=0.8)
    assert [item.id for item in pack.included] == [
        "graph:calc.py:4:multiply",
        "file:calc.py",
    ]
    assert not pack.omissions


def test_protected_whole_files_are_never_threshold_omitted(tmp_path: Path) -> None:
    """MET-TOKENS: protected content survives the threshold — protection wins
    over relevance scoring (protected spans kept must stay 100%)."""
    items = [
        _evidence(
            "graph:calc.py:4:multiply",
            source="calc.py:4",
            source_type="graph_symbol",
            confidence=0.9,
        ),
        _evidence(
            "file:pinned.py",
            source="pinned.py",
            source_type="file",
            confidence=0.2,
            protected=True,
        ),
    ]
    pack = _compile(items, tmp_path, threshold=0.8)
    assert "file:pinned.py" in [item.id for item in pack.included]


def test_threshold_is_inert_without_symbol_evidence(tmp_path: Path) -> None:
    """MET-TOKENS: with no symbol representation in the plan, whole files are
    the only content available — the threshold must not empty the pack."""
    items = [
        _evidence("file:calc.py", source="calc.py", source_type="file", confidence=0.55),
        _evidence("file:notes.md", source="notes.md", source_type="file", confidence=0.4),
    ]
    pack = _compile(items, tmp_path, threshold=0.8)
    assert {item.id for item in pack.included} == {"file:calc.py", "file:notes.md"}


def test_no_threshold_keeps_legacy_behavior(tmp_path: Path) -> None:
    """MET-TOKENS: passing no threshold reproduces the legacy pack exactly."""
    items = [
        _evidence(
            "graph:calc.py:4:multiply",
            source="calc.py:4",
            source_type="graph_symbol",
            confidence=0.9,
        ),
        _evidence(
            "file:distractor.py", source="distractor.py", source_type="file", confidence=0.33
        ),
    ]
    pack = _compile(items, tmp_path, threshold=None)
    assert {item.id for item in pack.included} == {
        "graph:calc.py:4:multiply",
        "file:distractor.py",
    }
