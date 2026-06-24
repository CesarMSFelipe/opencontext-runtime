"""Tests for VerifyReport.compute_verdict (CAP6 — verify report aggregation).

VerifyReport.compute_verdict(matrix) returns aggregated counts plus an
overall verdict: PASS when every entry is PASS, MISSING otherwise.
"""

from __future__ import annotations

from opencontext_core.verify.compliance import (
    ComplianceMatrix,
    VerificationKind,
    VerificationStatus,
)
from opencontext_core.verify.report import VerifyReport


def test_compute_verdict_all_pass_is_pass() -> None:
    matrix = ComplianceMatrix()
    matrix.add(
        "REQ-01",
        kind=VerificationKind.TEST,
        reference="t/a.py",
        status=VerificationStatus.PASS,
    )
    matrix.add(
        "REQ-02",
        kind=VerificationKind.GATE,
        reference="QualityGate",
        status=VerificationStatus.PASS,
    )

    report = VerifyReport.compute_verdict(matrix)

    assert report.passed == 2
    assert report.missing == 0
    assert report.failed == 0
    assert report.pending == 0
    assert report.total == 2
    assert report.verdict == "PASS"


def test_compute_verdict_one_missing_is_missing() -> None:
    matrix = ComplianceMatrix()
    matrix.add(
        "REQ-05",
        kind=VerificationKind.TEST,
        reference="t/x.py",
        status=VerificationStatus.PASS,
    )
    matrix.add("REQ-06", kind=VerificationKind.MISSING, status=VerificationStatus.MISSING)

    report = VerifyReport.compute_verdict(matrix)

    assert report.passed == 1
    assert report.missing == 1
    assert report.total == 2
    assert report.verdict == "MISSING"


def test_compute_verdict_fail_counts_as_failure() -> None:
    matrix = ComplianceMatrix()
    matrix.add(
        "REQ-10",
        kind=VerificationKind.GATE,
        reference="QualityGate",
        status=VerificationStatus.FAIL,
    )

    report = VerifyReport.compute_verdict(matrix)

    assert report.failed == 1
    assert report.passed == 0
    assert report.verdict == "MISSING"


def test_compute_verdict_pending_counts_separately() -> None:
    matrix = ComplianceMatrix()
    matrix.add(
        "REQ-A",
        kind=VerificationKind.TEST,
        reference="x",
        status=VerificationStatus.PASS,
    )
    matrix.add(
        "REQ-B",
        kind=VerificationKind.TEST,
        reference="y",
        status=VerificationStatus.PENDING,
    )

    report = VerifyReport.compute_verdict(matrix)

    assert report.passed == 1
    assert report.pending == 1
    assert report.total == 2
    assert report.verdict == "MISSING"


def test_compute_verdict_empty_matrix_is_pass() -> None:
    report = VerifyReport.compute_verdict(ComplianceMatrix())
    assert report.total == 0
    assert report.verdict == "PASS"