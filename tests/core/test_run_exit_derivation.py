"""Canonical state + exit-code derivation for workflow runs (RUN_STATE_CONTRACT).

Unit tests for the pure mapping used by `opencontext run`: OC Flow / harness
terminal vocabulary -> canonical state -> documented exit code (AC-009..AC-012).
"""

from __future__ import annotations

import pytest

from opencontext_core.models.canonical_status import (
    CanonicalStatus,
    exit_code_for_run,
    to_canonical,
)


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        ("completed", "passed"),
        ("escalated", "failed"),
        ("needs_provider", "needs_executor"),
        ("needs_verification", "failed"),
        ("needs_user_edit", "needs_approval"),
        ("tdd_violation", "blocked"),
        ("completed_with_warnings", "passed"),
        ("scaffolded", "not_applicable"),
    ],
)
def test_oc_flow_vocabulary_maps_to_canonical(legacy: str, expected: str) -> None:
    assert to_canonical(legacy) is CanonicalStatus(expected)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("passed", 0),
        ("completed", 0),
        ("not_applicable", 0),
        ("failed", 1),
        ("blocked", 1),
        ("cancelled", 1),
        ("needs_context", 1),
        ("needs_configuration", 3),
        ("needs_approval", 4),
        ("needs_executor", 5),
        ("needs_provider", 5),
        ("escalated", 1),
    ],
)
def test_exit_code_for_run_base_mapping(status: str, expected: int) -> None:
    assert exit_code_for_run(status) == expected


def test_verification_failure_earns_exit_8() -> None:
    assert exit_code_for_run("escalated", verification_failed=True) == 8
    assert exit_code_for_run("failed", verification_failed=True) == 8


def test_verification_flag_does_not_touch_non_failed_states() -> None:
    assert exit_code_for_run("needs_executor", verification_failed=True) == 5
    assert exit_code_for_run("passed", verification_failed=False) == 0


def test_tdd_violation_earns_exit_6() -> None:
    assert exit_code_for_run("tdd_violation", tdd_violation=True) == 6
    assert exit_code_for_run("blocked", tdd_violation=True) == 6


def test_tdd_violation_never_downgrades_a_pass() -> None:
    # A passed run is by definition not a violation; the flag must not fire.
    assert exit_code_for_run("passed", tdd_violation=False) == 0


def test_unknown_status_fails_closed() -> None:
    assert exit_code_for_run("no-such-status") == 1
