"""TDDEvidenceReport — trace requirements to test files and surface coverage gaps.

A requirement is *covered* when at least one test file references its REQ-N id
inside the project's tests directory. Requirements with no linked test are
surfaced with ``covered: False`` so reviewers see what's missing.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.tdd.evidence import TDDEvidenceReport


def _write_test(root: Path, relpath: str, body: str) -> Path:
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_build_marks_covered_when_test_references_req(tmp_path: Path) -> None:
    _write_test(tmp_path, "tests/test_req01.py", "def test_x(): # REQ-01\n  assert True\n")
    report = TDDEvidenceReport.build(requirements=["REQ-01"], tests_root=tmp_path)
    assert report.entries[0].req_id == "REQ-01"
    assert report.entries[0].covered is True
    assert any("test_req01.py" in p for p in report.entries[0].test_paths)


def test_build_marks_uncovered_when_no_test(tmp_path: Path) -> None:
    report = TDDEvidenceReport.build(requirements=["REQ-99"], tests_root=tmp_path)
    assert report.entries[0].covered is False
    assert report.entries[0].test_paths == []


def test_build_reports_missing_requirements(tmp_path: Path) -> None:
    report = TDDEvidenceReport.build(
        requirements=["REQ-01", "REQ-02"],
        tests_root=tmp_path,
    )
    uncovered = [e for e in report.entries if not e.covered]
    assert {e.req_id for e in uncovered} == {"REQ-01", "REQ-02"}


def test_build_with_partial_coverage(tmp_path: Path) -> None:
    _write_test(tmp_path, "tests/test_a.py", "# references REQ-10 here\n")
    report = TDDEvidenceReport.build(
        requirements=["REQ-10", "REQ-11"],
        tests_root=tmp_path,
    )
    by_req = {e.req_id: e.covered for e in report.entries}
    assert by_req == {"REQ-10": True, "REQ-11": False}


def test_build_aggregates_multiple_tests_for_one_req(tmp_path: Path) -> None:
    _write_test(tmp_path, "tests/test_a.py", "# REQ-50\n")
    _write_test(tmp_path, "tests/test_b.py", "# REQ-50\n")
    report = TDDEvidenceReport.build(requirements=["REQ-50"], tests_root=tmp_path)
    entry = report.entries[0]
    assert entry.covered is True
    assert len(entry.test_paths) == 2