"""Tests for AICX bytecode: compile → validate → decode → roundtrip."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.context.bytecode import (
    AICXCompiler,
    AICXDecoder,
    AICXValidator,
    compute_metrics,
)
from opencontext_core.context.bytecode.renderer import AICXRenderer
from opencontext_core.models.context import DataClassification
from opencontext_core.retrieval.contracts import (
    EvidenceItem,
    EvidencePlan,
    EvidenceRequest,
    FreshnessStatus,
    RetrievalSurface,
    TrustDecision,
)


def _make_plan(risk: str = "normal", evidence_count: int = 2) -> EvidencePlan:
    request = EvidenceRequest(
        query="fix crash in auth middleware",
        root=Path("."),
        surface=RetrievalSurface.RUNTIME,
        max_tokens=16000,
        risk_level=risk,
    )
    evidence = [
        EvidenceItem(
            id=f"e{i:03d}",
            content="def authenticate(): pass  # actual code body",
            source=f"src/auth/module_{i}.py",
            source_type="file",
            provenance={"method": "graph"},
            confidence=0.8 + i * 0.05,
            freshness=FreshnessStatus.CURRENT,
            surface=RetrievalSurface.RUNTIME,
            tokens=300 + i * 100,
            classification=DataClassification.INTERNAL,
        )
        for i in range(evidence_count)
    ]
    return EvidencePlan(
        request=request,
        evidence=evidence,
        fallback_actions=["index_project"],
        trust_decision=TrustDecision(status="sufficient", reason="coverage ok"),
        trace_id="test-trace-001",
        omissions=["vector_disabled"],
        source_surfaces=[RetrievalSurface.RUNTIME],
    )


class TestAICXCompiler:
    def test_compile_produces_bytecode(self):
        plan = _make_plan()
        bc = AICXCompiler().compile(plan)
        assert bc.version == "AICX/1"
        assert bc.checksum
        assert bc.request_id
        ops = [i.op for i in bc.instructions]
        assert "REQ" in ops
        assert "EVID" in ops
        assert "TRUST" in ops

    def test_evidence_not_inlined(self):
        plan = _make_plan(evidence_count=3)
        bc = AICXCompiler().compile(plan)
        # No instruction should contain raw code content
        for instr in bc.instructions:
            for arg in instr.args:
                assert "def authenticate" not in arg

    def test_dictionary_deduplicates(self):
        plan = _make_plan(evidence_count=3)
        bc = AICXCompiler().compile(plan)
        # Dictionary values are unique
        values = list(bc.dictionary.values())
        assert len(values) == len(set(values))

    def test_high_risk_adds_security_gate(self):
        plan = _make_plan(risk="high")
        bc = AICXCompiler().compile(plan)
        gate_ops = [i for i in bc.instructions if i.op == "GATE"]
        gate_names = [g.args[0] for g in gate_ops]
        assert "security" in gate_names


class TestAICXValidator:
    def test_valid_bytecode_passes(self):
        bc = AICXCompiler().compile(_make_plan())
        report = AICXValidator().validate(bc)
        assert report.passed
        assert report.checksum_valid
        assert report.version_supported
        assert not report.errors

    def test_tampered_checksum_fails(self):
        bc = AICXCompiler().compile(_make_plan())
        bc = bc.model_copy(update={"checksum": "tampered"})
        report = AICXValidator().validate(bc)
        assert not report.passed
        assert not report.checksum_valid

    def test_unknown_version_fails(self):
        bc = AICXCompiler().compile(_make_plan())
        bc = bc.model_copy(update={"version": "AICX/99", "checksum": bc.checksum})
        report = AICXValidator().validate(bc)
        assert not report.version_supported


class TestAICXDecoder:
    def test_decode_restores_request(self):
        plan = _make_plan()
        bc = AICXCompiler().compile(plan)
        decoded = AICXDecoder().decode(bc)
        assert decoded.request.query == plan.request.query
        assert decoded.request.risk_level == plan.request.risk_level
        assert decoded.request.max_tokens == plan.request.max_tokens

    def test_decode_evidence_count_matches(self):
        plan = _make_plan(evidence_count=3)
        bc = AICXCompiler().compile(plan)
        decoded = AICXDecoder().decode(bc)
        assert len(decoded.evidence) == 3

    def test_decoded_content_is_empty(self):
        """Lazy expansion: content must not be inlined in decoded evidence."""
        plan = _make_plan()
        bc = AICXCompiler().compile(plan)
        decoded = AICXDecoder().decode(bc)
        for item in decoded.evidence:
            assert item.content == ""

    def test_decode_trust_decision(self):
        plan = _make_plan()
        bc = AICXCompiler().compile(plan)
        decoded = AICXDecoder().decode(bc)
        assert decoded.trust_decision.status == "sufficient"


class TestAICXRenderer:
    def test_text_contains_version(self):
        bc = AICXCompiler().compile(_make_plan())
        text = AICXRenderer().render_text(bc)
        assert text.startswith("AICX/1")

    def test_json_is_compact(self):
        bc = AICXCompiler().compile(_make_plan(evidence_count=2))
        json_out = AICXRenderer().render_json(bc)
        # No newlines in compact JSON
        assert "\n" not in json_out

    def test_compact_smaller_than_original_tokens(self):
        plan = _make_plan(evidence_count=5)
        bc = AICXCompiler().compile(plan)
        text = AICXRenderer().render_text(bc)
        # bytecode has no inline content — far fewer tokens than sum of evidence
        original_tokens = sum(item.tokens for item in plan.evidence)
        bytecode_tokens = len(text) // 4
        assert bytecode_tokens < original_tokens


class TestAICXMetrics:
    def test_token_reduction_positive(self):
        plan = _make_plan(evidence_count=4)
        bc = AICXCompiler().compile(plan)
        metrics = compute_metrics(plan, bc)
        assert metrics.original_tokens > 0
        assert metrics.bytecode_tokens > 0
        assert metrics.token_reduction_pct >= 0.0
        assert metrics.evidence_count == 4
        assert metrics.gate_count > 0
