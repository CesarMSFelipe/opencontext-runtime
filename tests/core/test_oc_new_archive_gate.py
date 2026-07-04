"""Tests for OcNewArchiveGate."""

from __future__ import annotations

import pytest

from opencontext_core.oc_new.archive_gate import OcNewArchiveGate


def test_gate_passes_when_all_present(tmp_path):
    gate = OcNewArchiveGate()
    for name in gate.REQUIRED:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    missing = gate.validate(tmp_path)
    assert missing == []


def test_gate_reports_missing(tmp_path):
    gate = OcNewArchiveGate()
    missing = gate.validate(tmp_path)
    assert set(missing) == set(gate.REQUIRED)


def test_gate_assert_raises_when_missing(tmp_path):
    gate = OcNewArchiveGate()
    with pytest.raises(RuntimeError, match="Cannot archive"):
        gate.assert_can_archive(tmp_path)


def test_gate_assert_passes_when_all_present(tmp_path):
    gate = OcNewArchiveGate()
    content = {
        "verify-report.json": '{"verdict": "PASS"}',
        "compliance-matrix.json": '{"passed": true}',
        "harness-report.json": '{"passed": true, "failures": []}',
    }
    for name in gate.REQUIRED:
        (tmp_path / name).write_text(content.get(name, "{}"), encoding="utf-8")
    gate.assert_can_archive(tmp_path)  # must not raise


def test_gate_requires_compliance_matrix(tmp_path):
    assert "compliance-matrix.json" in OcNewArchiveGate.REQUIRED


def test_gate_requires_harness_report(tmp_path):
    assert "harness-report.json" in OcNewArchiveGate.REQUIRED


def test_gate_fails_when_compliance_matrix_missing(tmp_path):
    gate = OcNewArchiveGate()
    for name in gate.REQUIRED:
        if name != "compliance-matrix.json":
            (tmp_path / name).write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"compliance-matrix\.json"):
        gate.assert_can_archive(tmp_path)


def test_gate_fails_when_harness_report_missing(tmp_path):
    gate = OcNewArchiveGate()
    for name in gate.REQUIRED:
        if name != "harness-report.json":
            (tmp_path / name).write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"harness-report\.json"):
        gate.assert_can_archive(tmp_path)


# --- Adversarial content gates: the artifact EXISTS but declares failure. -----
# This is the "a phase reports success but its own evidence contradicts it" mode
# (gentle-ai's sddstatus has ~15 such cases). File existence is not enough; the
# gate must read the content and refuse to archive a failing report.


def _write_required(tmp_path, **overrides):
    """Write every REQUIRED artifact as passing, then apply per-file overrides."""
    passing = {
        "verify-report.json": '{"verdict": "PASS"}',
        "compliance-matrix.json": '{"passed": true}',
        "harness-report.json": '{"passed": true, "failures": []}',
    }
    passing.update(overrides)
    for name in OcNewArchiveGate.REQUIRED:
        (tmp_path / name).write_text(passing.get(name, "{}"), encoding="utf-8")


def test_archive_blocked_when_verify_report_declares_fail(tmp_path):
    """verify-report.json present but verdict=FAIL must block archive."""
    _write_required(tmp_path, **{"verify-report.json": '{"verdict": "FAIL"}'})
    with pytest.raises(RuntimeError, match=r"verify-report\.json"):
        OcNewArchiveGate().assert_can_archive(tmp_path)


def test_archive_blocked_when_compliance_matrix_not_passed(tmp_path):
    """A forged PASS verdict cannot bypass a compliance matrix that says passed=false."""
    _write_required(tmp_path, **{"compliance-matrix.json": '{"passed": false}'})
    with pytest.raises(RuntimeError, match=r"compliance-matrix\.json"):
        OcNewArchiveGate().assert_can_archive(tmp_path)


def test_archive_blocked_when_harness_report_has_failures(tmp_path):
    """harness-report.json with passed=false and a failures list must block archive."""
    _write_required(
        tmp_path,
        **{"harness-report.json": '{"passed": false, "failures": ["test_add"]}'},
    )
    with pytest.raises(RuntimeError, match=r"harness-report\.json"):
        OcNewArchiveGate().assert_can_archive(tmp_path)


def test_archive_passes_on_canonical_all_green(tmp_path):
    """Positive anchor: all three artifacts declare success → archive allowed."""
    _write_required(tmp_path)
    OcNewArchiveGate().assert_can_archive(tmp_path)  # must not raise
