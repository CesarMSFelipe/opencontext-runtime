"""TAX-COUNTS: §21.1 suite taxonomy bands — met where honest, pinned where not.

DOC2 §21.1 targets: golden contracts 15-25, unit core 60-120, integration
narrow 20-40, total 120-220. Two of those are now enforced live (this module
pins the golden band; ``tests/unit/test_unit_timing.py`` pins the unit-core
band). The TOTAL and integration bands are deliberately NOT met: the §26
reduction pass (artifacts/test-reduction-report.md) verified every DELETE
candidate against the §26.3 rules and kept the larger suite on purpose. That
is a recorded deviation, not an accident — so this module also pins that the
deviation stays documented instead of silently forgotten.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO / "tests" / "golden"

#: §21.1 "Golden contracts" row.
GOLDEN_BAND = (15, 25)


def _golden_test_count() -> int:
    """Static count of collected golden tests (fixture repos are never collected)."""
    count = 0
    for path in sorted(GOLDEN_DIR.glob("test_*.py")):  # fixture repos live in subdirs
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test"
            ):
                count += 1
    return count


def test_golden_contract_suite_is_within_the_band() -> None:
    """TAX-COUNTS: the dedicated golden-contract suite holds 15-25 tests.

    §19.2/§21.1: the public-output contracts (version/status/run/memory/kg/sdd
    JSON) live as a curated suite in tests/golden — neither shrinking below the
    band (contracts uncovered) nor ballooning past it (snapshot creep)."""
    count = _golden_test_count()
    assert GOLDEN_BAND[0] <= count <= GOLDEN_BAND[1], (
        f"golden contract suite has {count} tests, outside the §21.1 band "
        f"{GOLDEN_BAND[0]}-{GOLDEN_BAND[1]}"
    )


def test_taxonomy_total_deviation_stays_documented() -> None:
    """TAX-COUNTS: the §21.1 total-count deviation is a recorded decision.

    The suite deliberately exceeds the 120-220 total band: the §26 reduction
    pass verified every DELETE candidate against §26.3 and kept them. That
    decision must stay auditable — this fails if the reduction report (the
    deviation record) disappears or stops recording the verification outcome."""
    report_path = REPO / "artifacts" / "test-reduction-report.md"
    assert report_path.is_file(), (
        "artifacts/test-reduction-report.md is the recorded §21.1 deviation — "
        "removing it un-documents why the suite exceeds 120-220 tests"
    )
    text = report_path.read_text(encoding="utf-8")
    assert "§26.3" in text, "the report must reference the §26.3 verification rules"
    assert "## Deleted" in text and "(none)" in text, (
        "the report must record the delete-pass outcome"
    )
