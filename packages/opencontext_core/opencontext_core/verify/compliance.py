"""ComplianceMatrix — maps each requirement to its verification artefact.

A *verification artefact* is the evidence that a requirement has been
satisfied: a pytest reference, a quality-gate result, or a manual
attestation. Missing requirements surface explicitly so the verify
phase can fail closed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class VerificationKind(StrEnum):
    """Source of evidence for a requirement."""

    TEST = "test"
    GATE = "gate"
    MANUAL = "manual"
    MISSING = "missing"


class VerificationStatus(StrEnum):
    """Outcome of the verification artefact."""

    PASS = "PASS"
    FAIL = "FAIL"
    MISSING = "MISSING"
    PENDING = "PENDING"


class VerificationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    kind: VerificationKind
    reference: str | None = None
    status: VerificationStatus = VerificationStatus.MISSING


class ComplianceMatrix(BaseModel):
    """In-memory mapping of requirement_id → VerificationEntry."""

    model_config = ConfigDict(extra="forbid")

    entries: list[VerificationEntry] = Field(default_factory=list)

    def add(
        self,
        requirement_id: str,
        *,
        kind: VerificationKind,
        reference: str | None = None,
        status: VerificationStatus = VerificationStatus.MISSING,
    ) -> VerificationEntry:
        entry = VerificationEntry(
            requirement_id=requirement_id,
            kind=kind,
            reference=reference,
            status=status,
        )
        self.entries.append(entry)
        return entry

    def lookup(self, requirement_id: str) -> VerificationEntry | None:
        for entry in self.entries:
            if entry.requirement_id == requirement_id:
                return entry
        return None

    def mark_status(self, requirement_id: str, *, status: VerificationStatus) -> None:
        for idx, entry in enumerate(self.entries):
            if entry.requirement_id == requirement_id:
                self.entries[idx] = entry.model_copy(update={"status": status})
                return

    def iter_entries(self) -> list[VerificationEntry]:
        return list(self.entries)


__all__ = [
    "ComplianceMatrix",
    "VerificationEntry",
    "VerificationKind",
    "VerificationStatus",
]
