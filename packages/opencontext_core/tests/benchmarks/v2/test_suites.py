"""Suites package surface — exposes 10 §A gate suites (7 implemented + 3 inherited)."""

from __future__ import annotations

from opencontext_core.benchmarks.v2.suites import (
    SUITE_IDS,
    get_suite,
)


def test_suite_ids_cover_ten_a_gates() -> None:
    # A1..A10
    expected = {f"A{i}" for i in range(1, 11)}
    assert expected.issubset(set(SUITE_IDS))


def test_get_suite_returns_callable() -> None:
    for sid in ("A1", "A9"):
        fn = get_suite(sid)
        assert callable(fn)
