"""VerifyReport — aggregated PASS/MISSING summary of a ComplianceMatrix.

A run is PASS iff every requirement has status PASS. Any MISSING, FAIL, or
PENDING downgrades the verdict to MISSING so the verify phase fails closed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from opencontext_core.verify.compliance import (
    ComplianceMatrix,
    VerificationStatus,
)


class VerifyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: int = 0
    failed: int = 0
    missing: int = 0
    pending: int = 0
    total: int = 0
    verdict: str = "PASS"

    @classmethod
    def compute_verdict(cls, matrix: ComplianceMatrix) -> VerifyReport:
        passed = failed = missing = pending = 0
        for entry in matrix.iter_entries():
            if entry.status == VerificationStatus.PASS:
                passed += 1
            elif entry.status == VerificationStatus.FAIL:
                failed += 1
            elif entry.status == VerificationStatus.PENDING:
                pending += 1
            else:
                missing += 1
        total = passed + failed + missing + pending
        verdict = (
            "PASS"
            if total > 0 and failed == 0 and missing == 0 and pending == 0
            else ("PASS" if total == 0 else "MISSING")
        )
        return cls(
            passed=passed,
            failed=failed,
            missing=missing,
            pending=pending,
            total=total,
            verdict=verdict,
        )


__all__ = ["VerifyReport"]
