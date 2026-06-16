"""AICX — Agent Incremental Context Exchange.

Lazy, verifiable context transport. Keeps context reference-based across
agent communication; expands to natural language only at the LLM boundary.
"""

from opencontext_core.context.bytecode.compiler import AICXCompiler
from opencontext_core.context.bytecode.decoder import AICXDecoder
from opencontext_core.context.bytecode.metrics import AICXMetrics, compute_metrics
from opencontext_core.context.bytecode.models import (
    BytecodeInstruction,
    BytecodeValidationReport,
    ContextBytecode,
    OpCode,
)
from opencontext_core.context.bytecode.renderer import AICXRenderer
from opencontext_core.context.bytecode.validator import AICXValidator

__all__ = [
    "AICXCompiler",
    "AICXDecoder",
    "AICXMetrics",
    "AICXRenderer",
    "AICXValidator",
    "BytecodeInstruction",
    "BytecodeValidationReport",
    "ContextBytecode",
    "OpCode",
    "compute_metrics",
]
