from __future__ import annotations

from opencontext_api.schemas import VerifiedContextResponse


def test_verified_context_schema_serializes_core_contract() -> None:
    body = VerifiedContextResponse.model_validate(
        {
            "trace_id": "trace-1",
            "context": "context",
            "evidence": [],
            "memory": [],
            "gates": [{"name": "coverage", "passed": True, "reason": "ok", "risks": []}],
            "risk_level": "normal",
            "trust_decision": {"status": "sufficient", "reason": "ok"},
            "token_usage": {"final_context_pack": 10},
            "omitted_sources": ["vector_disabled"],
        }
    )

    assert body.trace_id == "trace-1"
    assert body.gates[0]["name"] == "coverage"
