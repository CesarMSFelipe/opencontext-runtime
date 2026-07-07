"""TIME-SMOKE / TIME-FULL-ACC: in-lane timing budget guards.

ACCEPTANCE_CONTRACT.md "Timing budgets" (plan §21.1) sets wall-clock budgets
for the two acceptance lanes. Nothing enforced them: the lanes could creep past
their budgets and every run would still be green. These meta-tests are
reordered to run LAST in the lane (see ``pytest_collection_modifyitems`` in
``conftest.py``), so the elapsed session wall clock at that point IS the lane's
wall time.

Each guard applies only when the session actually IS the documented lane
(detected from the selected items), and skips otherwise — a partial selection
(single file, ``-k`` filter, whole-repo run) is not a lane and has no budget.
Guard meta-tests are excluded from the scenario counts they assert on.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

#: ACCEPTANCE_CONTRACT.md "Timing budgets" (plan §21.1).
SMOKE_BUDGET_SECONDS = 60.0
SMOKE_SIZE_BAND = (8, 12)
FULL_BUDGET_SECONDS = 300.0
FULL_SIZE_BAND = (25, 55)

_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "product-contract" / "ACCEPTANCE_CONTRACT.md"
)


def test_size_bands_match_acceptance_contract() -> None:
    """The enforcing constants track the ACCEPTANCE_CONTRACT.md timing table.

    Guards the drift that let AC-031 update the contract while the enforcing
    constant stayed behind: any band change must land in BOTH the contract
    table and this module, in the same commit.
    """
    if not _CONTRACT_PATH.exists():
        pytest.skip("contract doc not present (packaged/standalone run)")
    text = _CONTRACT_PATH.read_text(encoding="utf-8")
    dash = "[\u2013-]"  # the contract table separates band bounds with an en dash
    smoke = re.search(rf"\|\s*Smoke[^|]*\|\s*(\d+)\s*{dash}\s*(\d+) scenario tests", text)
    full = re.search(rf"\|\s*Full acceptance[^|]*\|\s*(\d+)\s*{dash}\s*(\d+) scenario tests", text)
    assert smoke and full, "ACCEPTANCE_CONTRACT.md timing-budget table rows not found"
    assert (int(smoke.group(1)), int(smoke.group(2))) == SMOKE_SIZE_BAND, (
        f"SMOKE_SIZE_BAND {SMOKE_SIZE_BAND} out of sync with contract "
        f"{smoke.group(1)}-{smoke.group(2)} — update both together"
    )
    assert (int(full.group(1)), int(full.group(2))) == FULL_SIZE_BAND, (
        f"FULL_SIZE_BAND {FULL_SIZE_BAND} out of sync with contract "
        f"{full.group(1)}-{full.group(2)} — update both together"
    )


def _lane_accounting(request: pytest.FixtureRequest) -> tuple[dict[str, int | bool], float]:
    config = request.config
    selection = getattr(config, "_oc_lane_selection", None)
    start = getattr(config, "_oc_lane_start", None)
    if selection is None or start is None:
        pytest.skip(
            "lane accounting unavailable (tests/acceptance/conftest.py was not "
            "loaded as an initial conftest for this invocation)"
        )
    return selection, float(start)


@pytest.mark.smoke
def test_smoke_lane_meets_size_and_time_budget(request: pytest.FixtureRequest) -> None:
    """TIME-SMOKE: the smoke lane runs 8-12 scenario tests in under 60 s.

    Applies to the documented lane invocation (`pytest tests/acceptance -m
    smoke`): every selected scenario carries the smoke marker and at least the
    lower size band is selected. A smoke lane that grows past 12 scenarios or
    creeps past the 60 s budget fails here instead of silently regressing.
    """
    selection, start = _lane_accounting(request)
    is_smoke_lane = (
        bool(selection["only_acceptance_selected"])
        and int(selection["scenario_count"]) >= SMOKE_SIZE_BAND[0]
        and int(selection["scenario_count"]) == int(selection["smoke_scenario_count"])
    )
    if not is_smoke_lane:
        pytest.skip("smoke budget applies to the pure smoke lane: pytest tests/acceptance -m smoke")

    assert int(selection["smoke_scenario_count"]) <= SMOKE_SIZE_BAND[1], (
        f"ACCEPTANCE_CONTRACT timing budgets: the smoke lane must stay at "
        f"{SMOKE_SIZE_BAND[0]}-{SMOKE_SIZE_BAND[1]} scenario tests, got "
        f"{selection['smoke_scenario_count']} — move slow scenarios to the full lane"
    )
    elapsed = time.monotonic() - start
    assert elapsed < SMOKE_BUDGET_SECONDS, (
        f"ACCEPTANCE_CONTRACT timing budgets: smoke lane took {elapsed:.1f}s, "
        f"budget is {SMOKE_BUDGET_SECONDS:.0f}s — profile the workflow-run "
        f"fixtures (they dominate the wall time) before adding scenarios"
    )


def test_full_acceptance_lane_meets_size_and_time_budget(request: pytest.FixtureRequest) -> None:
    """TIME-FULL-ACC: the full acceptance lane runs 25-55 scenario tests in under 5 min.

    Applies to the documented lane invocation (`pytest tests/acceptance`):
    only acceptance items are selected and at least the lower size band is
    present. Pins both the < 5 min wall budget and the suite-growth cap so
    duration and size drift fail loudly instead of accumulating.
    """
    selection, start = _lane_accounting(request)
    is_full_lane = (
        bool(selection["only_acceptance_selected"])
        and int(selection["scenario_count"]) >= FULL_SIZE_BAND[0]
        and int(selection["scenario_count"]) > int(selection["smoke_scenario_count"])
    )
    if not is_full_lane:
        pytest.skip("full-acceptance budget applies to the full lane: pytest tests/acceptance")

    assert int(selection["scenario_count"]) <= FULL_SIZE_BAND[1], (
        f"ACCEPTANCE_CONTRACT timing budgets: the full acceptance lane must stay at "
        f"{FULL_SIZE_BAND[0]}-{FULL_SIZE_BAND[1]} scenario tests, got "
        f"{selection['scenario_count']} — consolidate scenarios before adding more"
    )
    elapsed = time.monotonic() - start
    assert elapsed < FULL_BUDGET_SECONDS, (
        f"ACCEPTANCE_CONTRACT timing budgets: full acceptance lane took {elapsed:.1f}s, "
        f"budget is {FULL_BUDGET_SECONDS:.0f}s"
    )
