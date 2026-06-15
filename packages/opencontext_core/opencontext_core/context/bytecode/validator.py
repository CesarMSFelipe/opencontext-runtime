"""AICXValidator: checksum + structural validation."""

from __future__ import annotations

from opencontext_core.context.bytecode.compiler import _compute_checksum
from opencontext_core.context.bytecode.models import (
    VERSION,
    BytecodeValidationReport,
    ContextBytecode,
    OpCode,
)

_SUPPORTED_VERSIONS = {VERSION}
_KNOWN_OPS = {op.value for op in OpCode}


class AICXValidator:
    def validate(self, bc: ContextBytecode) -> BytecodeValidationReport:
        errors: list[str] = []
        warnings: list[str] = []

        version_supported = bc.version in _SUPPORTED_VERSIONS
        if not version_supported:
            errors.append(f"unsupported version: {bc.version}")

        recomputed = _compute_checksum(bc.version, bc.dictionary, bc.instructions)
        checksum_valid = recomputed == bc.checksum
        if not checksum_valid:
            errors.append(f"checksum mismatch: got {bc.checksum}, expected {recomputed}")

        ops = {instr.op for instr in bc.instructions}
        unknown_ops = ops - _KNOWN_OPS
        for op in unknown_ops:
            warnings.append(f"unknown opcode: {op}")

        if OpCode.REQUEST not in ops:
            errors.append("missing REQ instruction")
        if OpCode.TRUST not in ops:
            errors.append("missing TRUST instruction")

        # Warn on high-risk without security gate
        for instr in bc.instructions:
            if instr.op == OpCode.REQUEST:
                args = {a.split(":")[0]: a.split(":", 1)[1] for a in instr.args if ":" in a}
                if args.get("risk") == "high":
                    gate_names = [i.args[0] for i in bc.instructions if i.op == OpCode.GATE]
                    if "security" not in gate_names:
                        warnings.append("high-risk request missing security gate")

        passed = len(errors) == 0
        return BytecodeValidationReport(
            passed=passed,
            version_supported=version_supported,
            checksum_valid=checksum_valid,
            errors=errors,
            warnings=warnings,
        )
