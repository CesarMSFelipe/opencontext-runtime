"""Orphan check — traceability matrix gate (DoD #13).

The architecture traceability matrix is the single source of truth for
which requirements ship in a release. Two failure modes block the gate:

1. **Wrong location** — the matrix lives at
   ``docs/architecture/54-requirement-to-pr-traceability-matrix.md``
   (per DoD #13 + amendment-3); a regression to the old
   ``docs/OpenContext_Complete_Plans_and_Architecture_Book/`` path is a
   release blocker.
2. **PROPOSED status leaked** — the schema is
   ``Status ∈ {MET | DEFERRED | REJECTED}`` (DoD #13, no PROPOSED).
   Any row whose status is not in that closed set fails the gate.

Both checks are pure-data: the test parses the markdown table and asserts
the schema invariant. The companion unit tests for capability ids live in
``packages/opencontext_core/tests/benchmarks/v2/test_orphan_check.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = REPO_ROOT / "docs/architecture/54-requirement-to-pr-traceability-matrix.md"

#: Closed status set per DoD #13 — anything else is a release blocker.
ALLOWED_STATUSES: frozenset[str] = frozenset({"MET", "DEFERRED", "REJECTED"})

#: Legacy location that amendment-3 retired. The matrix MUST NOT live here.
LEGACY_LOCATION: Path = (
    REPO_ROOT
    / "docs/OpenContext_Complete_Plans_and_Architecture_Book"
    / "54-requirement-to-pr-traceability-matrix.md"
)

_TABLE_ROW_RE = re.compile(
    r"^\|\s+\*\*(?P<req>[^*]+)\*\*.*?\|\s+(?P<status>MET|PROPOSED|DEFERRED|REJECTED)\s+\|\s*$",
    re.MULTILINE,
)


def _parse_statuses(matrix: Path) -> list[tuple[str, str]]:
    """Return ``(requirement_id, status)`` for every requirement row in *matrix*.

    Skips the header row and section-heading rows. Only rows whose line
    matches :data:`_TABLE_ROW_RE` are returned — that pattern is strict
    enough to ignore table-of-contents lines and footnotes.
    """
    text = matrix.read_text(encoding="utf-8")
    return [(m.group("req"), m.group("status")) for m in _TABLE_ROW_RE.finditer(text)]


@pytest.fixture()
def matrix_path() -> Path:
    """Path to the canonical traceability matrix."""
    return MATRIX_PATH


def test_orphan_blocks_release() -> None:
    """The matrix exists at the canonical location.

    If this assertion fails, the matrix was reverted to the legacy
    ``docs/OpenContext_Complete_Plans_and_Architecture_Book/`` path or
    the new ``docs/architecture/`` file is missing. Either case is a
    release blocker per DoD #13.
    """
    assert MATRIX_PATH.is_file(), (
        f"Traceability matrix missing at canonical location: {MATRIX_PATH}. "
        f"Per DoD #13 it must live at docs/architecture/."
    )


def test_matrix_not_at_legacy_location() -> None:
    """The legacy location MUST NOT host the matrix anymore.

    A regression to ``docs/OpenContext_Complete_Plans_and_Architecture_Book/``
    is silent — the new location exists, but so does the old. We assert
    the old one is gone (or, if the old file is just a redirect note,
    not the matrix itself).
    """
    if LEGACY_LOCATION.exists():
        # Tolerate a tombstone-style note that links to the new location.
        text = LEGACY_LOCATION.read_text(encoding="utf-8")
        assert "docs/architecture/54-requirement-to-pr-traceability-matrix.md" in text, (
            f"Legacy matrix location still active: {LEGACY_LOCATION}. "
            f"Per DoD #13 the matrix lives at docs/architecture/."
        )


def test_no_proposed_rows(matrix_path: Path) -> None:
    """Zero rows may carry ``PROPOSED`` status (DoD #13: closed set).

    The matrix uses ``Status ∈ {MET | DEFERRED | REJECTED}``. Any row
    with a status outside that closed set is a release blocker.
    """
    if not matrix_path.is_file():
        pytest.skip(f"matrix not present at {matrix_path}")
    rows = _parse_statuses(matrix_path)
    bad = [(req, status) for req, status in rows if status not in ALLOWED_STATUSES]
    assert not bad, (
        "Traceability matrix contains forbidden status values "
        f"(allowed: {sorted(ALLOWED_STATUSES)}):\n"
        + "\n".join(f"  {req}: {status}" for req, status in bad)
    )


def test_status_legend_matches_dod_13(matrix_path: Path) -> None:
    """The matrix's status legend must declare the DoD #13 closed set.

    The legend text is a single line in the matrix header. We assert it
    declares the closed set, so a regression to ``MET | PROPOSED | DEFERRED``
    is caught by the gate.
    """
    if not matrix_path.is_file():
        pytest.skip(f"matrix not present at {matrix_path}")
    text = matrix_path.read_text(encoding="utf-8")
    # Accept either "Status ∈ {MET | DEFERRED | REJECTED}" (ideal) or a
    # narrative legend listing the same closed set.
    ideal = re.search(r"Status\s*∈\s*\{[^}]*MET[^}]*DEFERRED[^}]*REJECTED", text)
    narrative = re.search(r"Status.*MET.*DEFERRED.*REJECTED", text, re.DOTALL)
    assert ideal is not None or narrative is not None, (
        "Matrix status legend must declare `Status ∈ {MET | DEFERRED | REJECTED}` per DoD #13."
    )


def test_matrix_has_rows(matrix_path: Path) -> None:
    """Smoke check — the matrix must contain at least one requirement row.

    A zero-row matrix is a structural failure: the gate would pass on
    an empty file. This smoke test catches that case explicitly.
    """
    if not matrix_path.is_file():
        pytest.skip(f"matrix not present at {matrix_path}")
    rows = _parse_statuses(matrix_path)
    assert rows, (
        f"Traceability matrix at {matrix_path} has no requirement rows — "
        "the orphan check would silently pass on an empty matrix."
    )


def test_guard_flags_a_seeded_proposed_row(tmp_path: Path) -> None:
    """The detector itself MUST FAIL on a seeded PROPOSED row.

    Seed a fake matrix with one PROPOSED row and assert the gate
    catches it. Proves the primitive parser/walker is wired correctly.
    """
    fake = tmp_path / "matrix.md"
    fake.write_text(
        "# 54 — Test\n\n"
        "**Status legend:** `Status ∈ {MET | DEFERRED | REJECTED}`.\n\n"
        "| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |\n"
        "|---|---|---|---|---|---|---|\n"
        "| **XX-001** seeded | doc | pr | mod | tst | — | MET |\n"
        "| **XX-002** seeded | doc | pr | mod | tst | — | PROPOSED |\n",
        encoding="utf-8",
    )

    rows = _parse_statuses(fake)
    bad = [(req, status) for req, status in rows if status not in ALLOWED_STATUSES]
    assert bad, "parser must surface a PROPOSED row"
    # The regex captures the bold-wrapped id only (e.g. "XX-002"), not the
    # trailing descriptive text. PROPOSED is the only forbidden status here.
    assert bad == [("XX-002", "PROPOSED")]


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
