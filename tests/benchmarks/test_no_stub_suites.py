"""Meta-test (rule 4) — §A suites integrity gate.

Asserts:
1. ``all_suites()`` returns exactly 12 callable suites.
2. ``suites/__init__.py`` source contains no ``_stub`` factory.
3. ``A11`` (benchmark_evidence) runs and passes the self-referential integrity check.
4. All 12 suites exercise real behaviour — no pending entries.

All 12 §A suites are wired as of B3.  This file intentionally contains no
xfail markers: all four assertions must pass green.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.benchmarks.v2.suites import all_suites

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITES_INIT = (
    _REPO_ROOT
    / "packages/opencontext_core/opencontext_core/benchmarks/v2/suites/__init__.py"
)


# ---------------------------------------------------------------------------
# Test 1 — structural count
# ---------------------------------------------------------------------------


def test_all_suites_returns_twelve() -> None:
    """``all_suites()`` must return exactly 12 §A suite callables."""
    suites = all_suites()
    assert len(suites) == 12, (
        f"Expected 12 §A suites, got {len(suites)}: {sorted(suites)}"
    )


# ---------------------------------------------------------------------------
# Test 2 — grep-level: no _stub in source
# ---------------------------------------------------------------------------


def test_no_stub_factory_in_suites_init() -> None:
    """``suites/__init__.py`` must not contain the ``_stub`` factory.

    This is the primary RED gate in B1: the file currently has ``_stub``
    and this test fails until the factory is deleted.
    """
    assert _SUITES_INIT.is_file(), f"suites/__init__.py not found at {_SUITES_INIT}"
    source = _SUITES_INIT.read_text(encoding="utf-8")
    assert "_stub" not in source, (
        "``_stub`` factory found in suites/__init__.py — delete it and wire real callables"
    )


# ---------------------------------------------------------------------------
# Test 3 — A11 self-referential integrity check
# ---------------------------------------------------------------------------


def test_a11_benchmark_evidence_passes() -> None:
    """Running the A11 suite must return success=True (integrity gate).

    A11 inspects ``all_suites()`` itself: if any callable is still named
    ``_stub.<locals>.run``, A11 returns success=False.
    """
    suites = all_suites()
    assert "A11" in suites, "A11 must be registered in all_suites()"
    result = suites["A11"]()
    assert result.success, f"A11 integrity check failed: {result.detail}"


# ---------------------------------------------------------------------------
# Test 4 — all 12 suites must be real (B3 complete)
# ---------------------------------------------------------------------------


def test_all_twelve_suites_are_real() -> None:
    """No §A suite may use the _pending_suite factory once all 12 are wired.

    All 12 suites are wired as of B3.  Each suite callable must NOT be a
    ``_pending_suite.<locals>.run`` function (checked by A11 introspection and
    by the source guard in test 2).  Additionally, none of the §A suite IDs
    should resolve to a function whose ``__qualname__`` contains ``_pending``.
    """
    suites = all_suites()
    still_pending = [
        sid
        for sid, fn in suites.items()
        if "_pending" in getattr(fn, "__qualname__", "")
    ]
    assert not still_pending, (
        f"Suites still using _pending_suite factory: {still_pending}"
    )
