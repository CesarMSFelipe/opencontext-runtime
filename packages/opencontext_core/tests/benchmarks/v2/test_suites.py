"""Suites package surface — exposes 12 §A benchmark suites (1.0 release)."""

from __future__ import annotations

from opencontext_core.benchmarks.v2.suites import (
    SUITE_IDS,
    all_suites,
    get_suite,
)


def test_suite_ids_cover_twelve_a_suites() -> None:
    """SUITE_IDS includes all twelve §A suites for the 1.0 release."""
    expected = {f"A{i}" for i in range(1, 13)}
    assert expected.issubset(set(SUITE_IDS))


def test_get_suite_returns_callable() -> None:
    for sid in ("A1", "A6", "A12"):
        fn = get_suite(sid)
        assert callable(fn)


def test_all_suites_returns_twelve() -> None:
    """``all_suites()`` returns a dict of all twelve suite callables."""
    suites = all_suites()
    assert len(suites) >= 12
