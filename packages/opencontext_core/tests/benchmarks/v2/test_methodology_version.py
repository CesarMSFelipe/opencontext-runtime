"""Methodology stamp — version that gates the benchmark report.

The benchmark release verdict is stamped with the methodology version
that produced the run. The stamp is a dotted ``YYYY.MM.DD`` value;
regressing it blocks the verdict. This file pins the format and the
current value.
"""

from __future__ import annotations

import pytest

from opencontext_core.benchmarks.v2.methodology import STAMP


def test_stamp_format() -> None:
    """The stamp is a dotted ``YYYY.MM.DD`` value with three numeric parts."""
    parts = STAMP.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)
    year, month, day = parts
    assert len(year) == 4
    assert 1 <= int(month) <= 12
    assert 1 <= int(day) <= 31


def test_stamp_value_is_2026_07_01() -> None:
    """The current methodology stamp is ``2026.07.01`` for the 1.0 release."""
    assert STAMP == "2026.07.01"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
