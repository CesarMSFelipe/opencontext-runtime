"""AICX metrics: token savings, compression ratio, roundtrip loss."""

from __future__ import annotations

from pydantic import BaseModel

from opencontext_core.context.bytecode.models import ContextBytecode, OpCode
from opencontext_core.context.bytecode.renderer import AICXRenderer
from opencontext_core.retrieval.contracts import EvidencePlan


class AICXMetrics(BaseModel):
    original_tokens: int
    bytecode_tokens: int
    evidence_count: int
    gate_count: int
    dictionary_entries: int
    instruction_count: int
    compression_ratio: float  # original / bytecode
    token_reduction_pct: float
    decode_time_ms: float = 0.0
    roundtrip_loss: bool = False  # True if decoded plan differs structurally


def compute_metrics(
    plan: EvidencePlan,
    bc: ContextBytecode,
    *,
    decode_time_ms: float = 0.0,
    roundtrip_loss: bool = False,
) -> AICXMetrics:
    original_tokens = sum(item.tokens for item in plan.evidence)
    bytecode_text = AICXRenderer().render_text(bc)
    # ponytail: rough estimate — 1 token ≈ 4 chars
    bytecode_tokens = max(1, len(bytecode_text) // 4)

    ratio = original_tokens / bytecode_tokens if bytecode_tokens else 0.0
    reduction = max(0.0, (1 - bytecode_tokens / original_tokens) * 100) if original_tokens else 0.0

    evidence_count = sum(1 for i in bc.instructions if i.op == OpCode.EVIDENCE)
    gate_count = sum(1 for i in bc.instructions if i.op == OpCode.GATE)

    return AICXMetrics(
        original_tokens=original_tokens,
        bytecode_tokens=bytecode_tokens,
        evidence_count=evidence_count,
        gate_count=gate_count,
        dictionary_entries=len(bc.dictionary),
        instruction_count=len(bc.instructions),
        compression_ratio=round(ratio, 2),
        token_reduction_pct=round(reduction, 1),
        decode_time_ms=decode_time_ms,
        roundtrip_loss=roundtrip_loss,
    )
