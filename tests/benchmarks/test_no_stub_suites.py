"""Meta-test (rule 4) — §A suites integrity gate.

Asserts:
1. ``all_suites()`` returns exactly 12 callable suites.
2. ``suites/__init__.py`` source contains no ``_stub`` factory.
3. ``A11`` (benchmark_evidence) runs and passes the self-referential integrity check.
4. (xfail until B3) All 12 suites exercise real behaviour — no pending entries.

The test LANDS RED in B1 because ``suites/__init__.py`` still has ``_stub`` before
the B1 implementation commits. After B1 the first three assertions are GREEN; the
xfail covers suites pending B2/B3 and is REMOVED in the batch that completes all 12.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.benchmarks.v2.suites import all_suites

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITES_INIT = (
    _REPO_ROOT
    / "packages/opencontext_core/opencontext_core/benchmarks/v2/suites/__init__.py"
)

# Suites not yet real after B1 — replaced with real behaviour in B2/B3.
_PENDING_AFTER_B1: frozenset[str] = frozenset(
    {"A2", "A3", "A4", "A7", "A8", "A9", "A10", "A12"}
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
# Test 4 — xfail until B3: all suites must be real
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "A2 A3 A4 A7 A8 A9 A10 A12 are honest-fail pending suites — "
        "wired in B2/B3. Remove this xfail when all 12 are real."
    ),
    strict=False,
)
def test_all_twelve_suites_are_real() -> None:
    """No §A suite may be a pending placeholder when all 12 are implemented.

    This xfail is removed by the B3 agent once every suite exercises real behaviour.
    """
    suites = all_suites()
    still_pending = [sid for sid in _PENDING_AFTER_B1 if sid in suites]
    assert not still_pending, f"Suites still pending: {still_pending}"
