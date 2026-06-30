"""Behavior tests for the quality shared-vocabulary module (``quality.models``).

These assert the load-bearing contract every sibling module relies on:

* ``finding_key`` is deterministic, POSIX-normalized, and bucket-aware (the SINGLE
  ratchet key shared by baseline + evaluator).
* ``HealthScore.score`` is an integer in basis points and ``delta`` is exact.
* ``QualityMetrics`` round-trips losslessly through dict/JSON.
* ``QualityReport`` maps to the ci-check report schema and to the correct exit code.
* ``to_check_result`` / ``to_gate_status`` reduce findings/verdicts correctly.

All filesystem work is confined to ``tmp_path``; nothing reads or writes the real
``~/.opencontext`` or the repo ``.opencontext``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.harness.models import GateStatus
from opencontext_core.quality.ci_checks import CheckResult, CheckSeverity, CheckStatus
from opencontext_core.quality.models import (
    Finding,
    HealthScore,
    QualityMetrics,
    QualityReport,
    RuleVerdict,
    Severity,
    finding_key,
    to_check_result,
    to_gate_status,
)

# --------------------------------------------------------------------------- #
# Severity alias: must be the SAME object as ci_checks.CheckSeverity, not a copy.
# --------------------------------------------------------------------------- #


def test_severity_is_the_ci_checks_enum_not_a_duplicate() -> None:
    assert Severity is CheckSeverity
    # A duplicate enum would break equality with ci_checks-produced severities.
    assert Severity.WARNING is CheckSeverity.WARNING


# --------------------------------------------------------------------------- #
# finding_key — the single ratchet/dedupe key.
# --------------------------------------------------------------------------- #


def test_finding_key_is_deterministic_for_same_inputs() -> None:
    a = finding_key("max_cc", "src/app.py", "do_work")
    b = finding_key("max_cc", "src/app.py", "do_work")
    assert a == b
    assert len(a) == 40  # sha1 hex digest


def test_finding_key_normalizes_windows_paths_to_posix() -> None:
    # A backslash path and its POSIX twin MUST produce the same key so the
    # ratchet survives a cross-platform baseline.
    win = finding_key("ruff", "src\\pkg\\mod.py", 12)
    posix = finding_key("ruff", "src/pkg/mod.py", 12)
    assert win == posix


def test_finding_key_distinguishes_rule_file_and_bucket() -> None:
    base = finding_key("max_cc", "src/app.py", "do_work")
    assert finding_key("max_cycles", "src/app.py", "do_work") != base  # rule differs
    assert finding_key("max_cc", "src/other.py", "do_work") != base  # file differs
    assert finding_key("max_cc", "src/app.py", "other_fn") != base  # bucket differs


def test_finding_key_treats_none_bucket_and_none_file_as_empty() -> None:
    # None must collapse to '' (not the string 'None') so absent file/line are stable.
    assert finding_key("r", None, None) == finding_key("r", "", "")
    assert finding_key("r", None, None) != finding_key("r", "None", "None")


def test_finding_key_line_vs_symbol_buckets_differ() -> None:
    # A line-bucketed key and a symbol-bucketed key for the same rule/file are
    # different findings (the bucket choice is meaningful).
    assert finding_key("max_cc", "a.py", 10) != finding_key("max_cc", "a.py", "fn")


# --------------------------------------------------------------------------- #
# QualityMetrics — lossless round-trip.
# --------------------------------------------------------------------------- #


def test_metrics_as_dict_round_trips_through_from_dict() -> None:
    m = QualityMetrics(
        cycles=2,
        god_files=3,
        max_cc=40,
        max_in_degree=15,
        max_out_degree=9,
        boundary_violations=1,
        max_depth=11,
        node_count=500,
        edge_count=1200,
    )
    assert QualityMetrics.from_dict(m.as_dict()) == m


def test_metrics_from_dict_defaults_missing_keys_to_zero() -> None:
    m = QualityMetrics.from_dict({"cycles": 5})
    assert m.cycles == 5
    assert m.god_files == 0
    assert m.edge_count == 0


def test_metrics_from_dict_coerces_json_floats_to_int() -> None:
    # JSON has no int/float distinction; a serialized 3.0 must come back as int 3.
    m = QualityMetrics.from_dict({"cycles": 3.0, "max_cc": 25.0})
    assert m.cycles == 3 and isinstance(m.cycles, int)
    assert m.max_cc == 25 and isinstance(m.max_cc, int)


def test_metrics_survive_a_full_json_text_round_trip(tmp_path: Path) -> None:
    m = QualityMetrics(cycles=1, god_files=2, max_cc=30)
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(m.as_dict()), encoding="utf-8")
    loaded = QualityMetrics.from_dict(json.loads(path.read_text(encoding="utf-8")))
    assert loaded == m


# --------------------------------------------------------------------------- #
# HealthScore — integer score, exact delta.
# --------------------------------------------------------------------------- #


def test_health_score_is_an_integer_in_basis_points() -> None:
    h = HealthScore(score=9180, metrics=QualityMetrics(), components={"cycles": 0})
    assert isinstance(h.score, int)
    assert 0 <= h.score <= 10000


def test_health_delta_is_exact_and_signed() -> None:
    better = HealthScore(score=9180, metrics=QualityMetrics(), components={})
    worse = HealthScore(score=9120, metrics=QualityMetrics(), components={})
    assert better.delta(worse) == 60  # improvement is positive
    assert worse.delta(better) == -60  # regression is negative
    assert better.delta(better) == 0


# --------------------------------------------------------------------------- #
# to_check_result — Finding -> ci_checks.CheckResult row.
# --------------------------------------------------------------------------- #


def test_to_check_result_maps_rule_to_check_name_and_marks_failed() -> None:
    f = Finding(
        rule="max_cc",
        severity=CheckSeverity.ERROR,
        message="too complex",
        file="src/app.py",
        line=42,
        suggestion="split it",
    )
    cr = to_check_result(f)
    assert isinstance(cr, CheckResult)
    assert cr.check_name == "max_cc"  # rule -> check_name
    assert cr.status == CheckStatus.FAILED  # a finding is always a violation row
    assert cr.severity == CheckSeverity.ERROR
    assert cr.message == "too complex"
    assert cr.file == "src/app.py"
    assert cr.line == 42
    assert cr.suggestion == "split it"


# --------------------------------------------------------------------------- #
# to_gate_status — reduce verdicts to a single gate status.
# --------------------------------------------------------------------------- #


def _verdict(status: CheckStatus, severity: CheckSeverity, *findings: Finding) -> RuleVerdict:
    return RuleVerdict(rule="r", status=status, severity=severity, findings=tuple(findings))


def test_to_gate_status_empty_is_passed() -> None:
    assert to_gate_status(()) == GateStatus.PASSED


def test_to_gate_status_all_passing_is_passed() -> None:
    v = _verdict(CheckStatus.PASSED, CheckSeverity.INFO)
    assert to_gate_status((v,)) == GateStatus.PASSED


def test_to_gate_status_warning_finding_yields_warning() -> None:
    warn_finding = Finding(rule="r", severity=CheckSeverity.WARNING, message="m")
    v = _verdict(CheckStatus.FAILED, CheckSeverity.WARNING, warn_finding)
    assert to_gate_status((v,)) == GateStatus.WARNING


def test_to_gate_status_error_finding_yields_failed() -> None:
    err_finding = Finding(rule="r", severity=CheckSeverity.ERROR, message="m")
    v = _verdict(CheckStatus.FAILED, CheckSeverity.ERROR, err_finding)
    assert to_gate_status((v,)) == GateStatus.FAILED


def test_to_gate_status_critical_finding_yields_failed() -> None:
    crit = Finding(rule="r", severity=CheckSeverity.CRITICAL, message="m")
    v = _verdict(CheckStatus.FAILED, CheckSeverity.CRITICAL, crit)
    assert to_gate_status((v,)) == GateStatus.FAILED


def test_to_gate_status_error_dominates_warning() -> None:
    warn = _verdict(
        CheckStatus.FAILED,
        CheckSeverity.WARNING,
        Finding(rule="r", severity=CheckSeverity.WARNING, message="w"),
    )
    err = _verdict(
        CheckStatus.FAILED,
        CheckSeverity.ERROR,
        Finding(rule="r", severity=CheckSeverity.ERROR, message="e"),
    )
    assert to_gate_status((warn, err)) == GateStatus.FAILED


def test_to_gate_status_errored_verdict_is_blocking() -> None:
    # A verdict whose own status is ERROR (the tool/rule itself failed) blocks.
    v = RuleVerdict(rule="r", status=CheckStatus.ERROR, severity=CheckSeverity.WARNING)
    assert to_gate_status((v,)) == GateStatus.FAILED


def test_to_gate_status_skipped_error_severity_does_not_block() -> None:
    # An error-severity rule that was SKIPPED (never ran) must not fail the gate —
    # degrade honestly: a skip is not a failure.
    v = RuleVerdict(rule="r", status=CheckStatus.SKIPPED, severity=CheckSeverity.ERROR)
    assert to_gate_status((v,)) == GateStatus.PASSED


# --------------------------------------------------------------------------- #
# QualityReport — exit code + ci-check report shape.
# --------------------------------------------------------------------------- #


def _report(
    status: GateStatus,
    findings: tuple[Finding, ...],
    verdicts: tuple[RuleVerdict, ...],
    *,
    baseline: HealthScore | None = None,
) -> QualityReport:
    health = HealthScore(score=9000, metrics=QualityMetrics(cycles=1), components={"cycles": 400})
    return QualityReport(
        status=status,
        findings=findings,
        verdicts=verdicts,
        health=health,
        baseline_health=baseline,
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (GateStatus.PASSED, 0),
        (GateStatus.SKIPPED, 0),  # skipped is non-blocking
        (GateStatus.WARNING, 1),  # warning still surfaces a nonzero exit
        (GateStatus.FAILED, 1),
    ],
)
def test_report_exit_code_follows_gate_status(status: GateStatus, expected: int) -> None:
    assert _report(status, (), ()).exit_code == expected


def test_report_to_report_dict_counts_match_findings_and_verdicts() -> None:
    findings = (
        Finding(rule="max_cc", severity=CheckSeverity.ERROR, message="e1", file="a.py", line=1),
        Finding(rule="ruff", severity=CheckSeverity.WARNING, message="w1", file="b.py", line=2),
        Finding(rule="bad", severity=CheckSeverity.CRITICAL, message="c1", file="c.py", line=3),
    )
    verdicts = (
        RuleVerdict(rule="max_cc", status=CheckStatus.FAILED, severity=CheckSeverity.ERROR),
        RuleVerdict(rule="ruff", status=CheckStatus.PASSED, severity=CheckSeverity.WARNING),
    )
    report = _report(GateStatus.FAILED, findings, verdicts)
    out = report.to_report_dict()

    summary = out["summary"]
    assert summary["total_checks"] == 2  # one per verdict
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["errors"] == 2  # error + critical findings both count as errors
    assert summary["warnings"] == 1
    assert summary["success"] is False  # FAILED is not ok

    # results carry one row per finding with the ci-check row keys.
    assert len(out["results"]) == 3
    row = out["results"][0]
    assert set(row) == {"check", "status", "severity", "message", "file", "line", "suggestion"}
    assert row["check"] == "max_cc"
    assert row["severity"] == "error"


def test_report_to_report_dict_success_true_when_status_ok() -> None:
    out = _report(GateStatus.PASSED, (), ()).to_report_dict()
    assert out["summary"]["success"] is True
    assert out["status"] == "not_applicable"


def test_report_to_report_dict_failed_checks_make_success_false() -> None:
    verdicts = (RuleVerdict(rule="r", status=CheckStatus.FAILED, severity=CheckSeverity.ERROR),)
    out = _report(GateStatus.SKIPPED, (), verdicts).to_report_dict()
    assert out["summary"]["failed"] == 1
    assert out["summary"]["success"] is False


def test_report_to_report_dict_skipped_checks_not_failed() -> None:
    verdicts = (RuleVerdict(rule="r", status=CheckStatus.SKIPPED, severity=CheckSeverity.WARNING),)
    out = _report(GateStatus.SKIPPED, (), verdicts).to_report_dict()
    assert out["status"] == "not_applicable"
    assert out["summary"]["failed"] == 0


def test_report_to_report_dict_delta_reflects_baseline() -> None:
    baseline = HealthScore(score=9100, metrics=QualityMetrics(), components={})
    # _report sets current health.score == 9000, so delta = 9000 - 9100 = -100.
    out = _report(GateStatus.WARNING, (), (), baseline=baseline).to_report_dict()
    assert out["delta"] == -100
    assert out["health"]["delta"] == -100
    assert out["health"]["score"] == 9000


def test_report_to_report_dict_delta_is_zero_without_baseline() -> None:
    out = _report(GateStatus.PASSED, (), ()).to_report_dict()
    assert out["delta"] == 0


def test_report_to_report_dict_is_json_serializable(tmp_path: Path) -> None:
    # The MCP tool + CLI both json.dumps this; prove it is JSON-safe primitives
    # by writing it to a tmp file and reading it back unchanged.
    findings = (
        Finding(rule="max_cc", severity=CheckSeverity.ERROR, message="e", file="a.py", line=5),
    )
    verdicts = (
        RuleVerdict(rule="max_cc", status=CheckStatus.FAILED, severity=CheckSeverity.ERROR),
    )
    out = _report(GateStatus.FAILED, findings, verdicts).to_report_dict()
    path = tmp_path / "report.json"
    path.write_text(json.dumps(out), encoding="utf-8")
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded == out


# --------------------------------------------------------------------------- #
# Frozen-dataclass invariants — these types are immutable value objects.
# --------------------------------------------------------------------------- #


def test_finding_is_frozen() -> None:
    f = Finding(rule="r", severity=CheckSeverity.INFO, message="m")
    with pytest.raises((AttributeError, TypeError)):
        f.rule = "changed"  # type: ignore[misc]


def test_finding_metadata_defaults_are_independent_instances() -> None:
    a = Finding(rule="a", severity=CheckSeverity.INFO, message="m")
    b = Finding(rule="b", severity=CheckSeverity.INFO, message="m")
    a.metadata["k"] = "v"
    assert b.metadata == {}  # default_factory, not a shared mutable default


def test_quality_metrics_carries_loc_gini_report_only() -> None:
    from opencontext_core.quality.models import QualityMetrics

    m = QualityMetrics(loc_gini_bp=4200)
    d = m.as_dict()
    assert d["loc_gini_bp"] == 4200
    # Round-trips through the dict (e.g. baseline persistence) losslessly.
    assert QualityMetrics.from_dict(d).loc_gini_bp == 4200
    # A missing key defaults to 0, so older baselines stay loadable.
    assert QualityMetrics.from_dict({}).loc_gini_bp == 0
