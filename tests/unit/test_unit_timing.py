"""TIME-UNIT: in-lane timing budget guard for the unit-core lane.

Plan §21.1 budgets the "Unit core algorithms" suite at 60-120 tests in under
10 s. ``tests/unit`` is the canonical unit-core lane for that row (other
unit-style directories — ``tests/core``, ``packages/*/tests`` — are package
suites outside this band). The guard is reordered to run LAST in the lane (see
``conftest.py``), so the elapsed session wall clock at that point is the lane's
wall time. It applies only when the session is the documented lane invocation
(`pytest tests/unit`) and skips for partial or whole-repo selections.
"""

from __future__ import annotations

import time

import pytest

#: Plan §21.1 "Unit core algorithms" row.
UNIT_BUDGET_SECONDS = 10.0
UNIT_SIZE_BAND = (60, 120)


def test_unit_core_lane_meets_size_and_time_budget(request: pytest.FixtureRequest) -> None:
    """TIME-UNIT: the unit-core lane (tests/unit) runs 60-120 tests in under 10 s.

    Fails when the lane outgrows the 120-test band or its wall clock creeps
    past the 10 s budget — a slow "fast lane" silently stops being run.
    """
    config = request.config
    selection = getattr(config, "_oc_unit_lane_selection", None)
    start = getattr(config, "_oc_unit_lane_start", None)
    if selection is None or start is None:
        pytest.skip(
            "lane accounting unavailable (tests/unit/conftest.py was not loaded "
            "as an initial conftest for this invocation)"
        )
    is_unit_lane = (
        bool(selection["only_unit_selected"])
        and int(selection["scenario_count"]) >= UNIT_SIZE_BAND[0]
    )
    if not is_unit_lane:
        pytest.skip("unit-core budget applies to the full lane: pytest tests/unit")

    assert int(selection["scenario_count"]) <= UNIT_SIZE_BAND[1], (
        f"plan §21.1: the unit-core lane must stay at {UNIT_SIZE_BAND[0]}-"
        f"{UNIT_SIZE_BAND[1]} tests, got {selection['scenario_count']} — split "
        f"slow or integration-shaped tests out of tests/unit"
    )
    elapsed = time.monotonic() - float(start)
    assert elapsed < UNIT_BUDGET_SECONDS, (
        f"plan §21.1: unit-core lane took {elapsed:.2f}s, budget is "
        f"{UNIT_BUDGET_SECONDS:.0f}s — tests/unit must stay subprocess- and IO-light"
    )
