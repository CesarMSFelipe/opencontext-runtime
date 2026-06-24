"""Tests for ComplianceMatrix (CAP6 — Verify, Compliance, Learning).

ComplianceMatrix maps each requirement to its verification artefact
(test, gate, or manual attestation). Spec scenarios:
  REQ-05 has a linked test that passes -> status PASS.
  REQ-06 has no linked artefact        -> status MISSING.
"""

from __future__ import annotations

from opencontext_core.verify.compliance import (
    ComplianceMatrix,
    VerificationEntry,
    VerificationKind,
)


def test_matrix_maps_passed_test_to_pass() -> None:
    matrix = ComplianceMatrix()
    matrix.add("REQ-05", kind=VerificationKind.TEST, reference="tests/x/test_foo.py::test_bar")
    matrix.mark_status("REQ-05", status="PASS")

    entry = matrix.lookup("REQ-05")
    assert entry is not None
    assert entry.requirement_id == "REQ-05"
    assert entry.kind == VerificationKind.TEST
    assert entry.reference == "tests/x/test_foo.py::test_bar"
    assert entry.status == "PASS"


def test_matrix_untraced_requirement_is_missing() -> None:
    matrix = ComplianceMatrix()
    matrix.add("REQ-06", kind=VerificationKind.MISSING)

    entry = matrix.lookup("REQ-06")
    assert entry is not None
    assert entry.kind == VerificationKind.MISSING
    assert entry.status == "MISSING"
    assert entry.reference is None


def test_matrix_lookup_unknown_returns_none() -> None:
    matrix = ComplianceMatrix()
    assert matrix.lookup("REQ-99") is None


def test_matrix_entries_iterate_in_insertion_order() -> None:
    matrix = ComplianceMatrix()
    matrix.add("REQ-01", kind=VerificationKind.GATE, reference="RequirementsQualityGate")
    matrix.add("REQ-02", kind=VerificationKind.TEST, reference="tests/x.py")
    matrix.add("REQ-03", kind=VerificationKind.MANUAL, reference="reviewer@example.com")

    entries = list(matrix.iter_entries())
    assert [e.requirement_id for e in entries] == ["REQ-01", "REQ-02", "REQ-03"]
    assert entries[0].kind == VerificationKind.GATE
    assert entries[2].kind == VerificationKind.MANUAL


def test_verification_entry_round_trips_through_dump() -> None:
    entry = VerificationEntry(
        requirement_id="REQ-07",
        kind=VerificationKind.GATE,
        reference="TaskQualityGate",
        status="FAIL",
    )
    restored = VerificationEntry.model_validate(entry.model_dump())
    assert restored.requirement_id == "REQ-07"
    assert restored.kind == VerificationKind.GATE
    assert restored.status == "FAIL"