"""Lane timing accounting for the unit-core suite (TIME-UNIT, plan §21.1).

``tests/unit`` is the canonical "Unit core algorithms" lane: 60-120 tests in
under 10 s. This conftest records when the lane started and what was selected,
and reorders the guard meta-test in ``test_unit_timing.py`` to run LAST so the
elapsed wall clock it reads covers the whole lane.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

_UNIT_DIR = Path(__file__).resolve().parent
_TIMING_GUARD_FILE = "test_unit_timing.py"


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config._oc_unit_lane_start = time.monotonic()  # type: ignore[attr-defined]


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if getattr(config, "_oc_unit_lane_start", None) is None:
        # Fallback: for invocations where this conftest is not an initial
        # conftest (e.g. whole-repo runs) sessionstart never fired here.
        config._oc_unit_lane_start = time.monotonic()  # type: ignore[attr-defined]

    def _is_unit(item: pytest.Item) -> bool:
        path = Path(item.path).resolve()
        return _UNIT_DIR == path.parent or _UNIT_DIR in path.parents

    unit_items = [item for item in items if _is_unit(item)]
    guards = [item for item in unit_items if Path(item.path).name == _TIMING_GUARD_FILE]
    config._oc_unit_lane_selection = {  # type: ignore[attr-defined]
        "only_unit_selected": len(unit_items) == len(items),
        "scenario_count": len(unit_items) - len(guards),
    }
    # Run the timing guard last so its wall-clock reading covers the lane.
    for guard in guards:
        items.remove(guard)
        items.append(guard)
