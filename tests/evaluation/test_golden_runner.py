"""Golden-fixture benchmark runners (B4 / B5 / AVH-006).

Proves the five 1.0-minimum golden gates MEASURE honestly: a present fixture yields
``MET`` / ``FAILED`` (never ``NOT_MEASURED``), an absent fixture yields
``NOT_MEASURED`` (never a fake ``MET``), and all five run with NO live LLM provider.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from opencontext_core.evaluation.golden import (
    FIXTURE_DIRS,
    GOLDEN_ROOT,
    GOLDEN_SUITE_NAMES,
    GoldenSuite,
)
from opencontext_core.evaluation.models import GateStatus
from opencontext_core.evaluation.runner import (
    MANDATORY_GATES,
    DeclaredSuite,
    build_default_runner,
)

# The two provider-CI gates that stay NOT_MEASURED without a provider hook (Option A;
# VDM-008). sdd-formal-feature, plugin-compatibility and memory-usefulness now MEASURE
# provider-free (golden fixtures + seeded backend), so they are no longer deferred.
_DEFERRED = (
    "context-token-efficiency",
    "kg-retrieval-precision",
)


# Only the "first-run" suite runs a full harness pass (>=25s); the rest are fast.
# Mark just that param slow so `-m "not slow"` skips the one heavy instance without
# quarantining the cheap suites.
_MEASURE_SUITE_PARAMS = [
    pytest.param(name, marks=pytest.mark.slow) if name == "first-run" else name
    for name in GOLDEN_SUITE_NAMES
]


@pytest.mark.parametrize("name", _MEASURE_SUITE_PARAMS)
def test_each_golden_suite_measures(name: str) -> None:
    # A present fixture must produce a verdict — MET or FAILED, never NOT_MEASURED.
    report = GoldenSuite(name, GOLDEN_ROOT).run(Path("."))
    assert report.status in {GateStatus.MET, GateStatus.FAILED}
    assert report.measured is True
    assert report.suite == name and report.version


@pytest.mark.parametrize("name", GOLDEN_SUITE_NAMES)
def test_golden_suites_are_met_on_clean_fixtures(name: str) -> None:
    # On the shipped (correct) fixtures every wired gate is genuinely MET.
    report = GoldenSuite(name, GOLDEN_ROOT).run(Path("."))
    assert report.status is GateStatus.MET, f"{name}: {report.notes}"


def test_missing_fixture_is_not_measured_never_fake_met(tmp_path: Path) -> None:
    # No fixture directory under this root → honest NOT_MEASURED (fake-MET invariant).
    report = GoldenSuite("first-run", tmp_path).run(Path("."))
    assert report.status is GateStatus.NOT_MEASURED
    assert report.status is not GateStatus.MET


def test_first_run_and_policy_security_need_no_live_provider() -> None:
    # Both are provider-free by construction and must reach a verdict regardless.
    for name in ("first-run", "policy-security"):
        report = GoldenSuite(name, GOLDEN_ROOT).run(Path("."))
        assert report.status is GateStatus.MET, f"{name}: {report.notes}"


def test_resume_rollback_and_provider_fallback_measure() -> None:
    # AVH-006 1.0-minimum coverage: both core-promise gates move off NOT_MEASURED.
    for name in ("resume-rollback", "provider-fallback"):
        report = GoldenSuite(name, GOLDEN_ROOT).run(Path("."))
        assert report.status is GateStatus.MET, f"{name}: {report.notes}"


def test_oc_flow_bugfix_fails_when_unfixed(tmp_path: Path) -> None:
    # If the provider stub proposes NO edit, the seeded bug remains → the gate is
    # honestly FAILED (never a fake completed/MET).
    src = GOLDEN_ROOT / FIXTURE_DIRS["oc-flow-localized-bugfix"]
    dst = tmp_path / FIXTURE_DIRS["oc-flow-localized-bugfix"]
    shutil.copytree(src, dst)
    (dst / "provider_stub.json").write_text("[]\n", encoding="utf-8")  # no fix proposed
    report = GoldenSuite("oc-flow-localized-bugfix", tmp_path).run(Path("."))
    assert report.status is GateStatus.FAILED
    assert report.status is not GateStatus.MET


def test_build_default_runner_wires_golden_gates_and_keeps_deferred_declared() -> None:
    runner = build_default_runner()
    # All ten mandatory gates are registered.
    assert set(runner.list_suites()) >= set(MANDATORY_GATES)
    # Every golden gate (now including sdd-formal-feature + plugin-compatibility) is a
    # GoldenSuite, not the inert DeclaredSuite stub.
    for name in GOLDEN_SUITE_NAMES:
        suite = runner.suite(name)
        assert isinstance(suite, GoldenSuite), f"{name} should be wired to a GoldenSuite"
    # No mandatory gate is left as an inert DeclaredSuite — the two provider-CI gates are
    # wired suites that report NOT_MEASURED honestly without a provider hook.
    assert not any(isinstance(runner.suite(n), DeclaredSuite) for n in MANDATORY_GATES)


def test_deferred_gates_stay_not_measured_no_fake_met() -> None:
    runner = build_default_runner()
    for name in _DEFERRED:
        report = runner.run(name, ".")
        assert report.status is GateStatus.NOT_MEASURED, f"{name} must not fake a pass"


def test_expected_json_is_present_and_parseable() -> None:
    # Every shipped fixture declares its contract.
    for dirname in FIXTURE_DIRS.values():
        path = GOLDEN_ROOT / dirname / "expected.json"
        assert path.is_file(), f"missing expected.json for {dirname}"
        json.loads(path.read_text(encoding="utf-8"))
