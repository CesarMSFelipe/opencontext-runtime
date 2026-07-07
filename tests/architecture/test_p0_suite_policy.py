"""MET-TESTS: §29.3 P0/P1 suite policy — zero unlabelled tests, zero flaky tolerance.

DOC2 §29.3 sets two suite-health metrics that had detection but no gate:

* "Tests without an associated contract/bug ID: 0 in P0/P1 suites" —
  ``scripts/test_inventory.py`` (rule 7) only REPORTS requirement ids; nothing
  failed when an unlabelled test landed in a contract suite.
* "Flaky tests: 0 tolerated in P0" — the taxonomy quarantines flaky-marked
  tests (inventory rule 4), but nothing stopped a flaky marker or a pytest
  rerun plugin from creeping into the P0 lanes and masking flakes as green.

These are static AST/text gates: cheap, deterministic, no subprocesses.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: The P0/P1 suites of the plan's taxonomy: acceptance (level A), golden +
#: compat (level B contract surfaces). Fixture repos inside them are test DATA
#: (never collected — see each suite's collect_ignore) and are skipped.
P0_SUITES = ("tests/acceptance", "tests/golden", "tests/compat")

#: Contract/bug id: an uppercase prefix, a dash, and a specific token —
#: AC-007, SMOKE-004, TIME-UNIT, GAP-101, REQ-12, BUG-3, MET-TOKENS, ...
CONTRACT_ID = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-[A-Za-z0-9]+\b")

#: Directory names inside the suites that hold fixture repos, not suite tests.
FIXTURE_DIR_MARKERS = {"fixtures", "flip_baseline", "__pycache__"}


def _suite_test_files() -> list[Path]:
    files: list[Path] = []
    for suite in P0_SUITES:
        suite_dir = REPO / suite
        for path in sorted(suite_dir.rglob("test_*.py")):
            relative_parts = path.relative_to(suite_dir).parts[:-1]
            if set(relative_parts) & FIXTURE_DIR_MARKERS:
                continue
            # tests/golden fixture repos are direct subdirectories without
            # __init__.py (kg_call_graph_python/, first_run/, ...): suite tests
            # live in importable packages, fixture repos do not.
            if relative_parts and not (suite_dir / relative_parts[0] / "__init__.py").is_file():
                continue
            files.append(path)
    assert files, "P0/P1 suite scan found no test files — the layout moved?"
    return files


def _unlabelled_tests(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module_ok = bool(CONTRACT_ID.search(ast.get_docstring(tree) or ""))
    unlabelled: list[str] = []

    def visit(node: ast.AST, class_ok: bool) -> None:
        for child in getattr(node, "body", []):
            if isinstance(child, ast.ClassDef):
                ok = class_ok or bool(CONTRACT_ID.search(ast.get_docstring(child) or ""))
                visit(child, ok)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                child.name.startswith("test")
            ):
                doc = ast.get_docstring(child) or ""
                if not (CONTRACT_ID.search(doc) or class_ok or module_ok):
                    unlabelled.append(child.name)

    visit(tree, class_ok=False)
    return unlabelled


def test_every_p0_suite_test_carries_a_contract_or_bug_id() -> None:
    """MET-TESTS: zero tests without a contract/bug ID in the P0/P1 suites.

    Every test in acceptance/golden/compat must be traceable to a contract
    item or bug: an id like AC-007 / SMOKE-004 / GAP-101 in its own docstring,
    its class docstring, or its module docstring (§29.3 row 5)."""
    offenders = [
        f"{path.relative_to(REPO)}::{name}"
        for path in _suite_test_files()
        for name in _unlabelled_tests(path)
    ]
    assert not offenders, (
        "P0/P1 suite tests without a contract/bug id (add the covered id to the "
        f"docstring, e.g. 'AC-007: ...'): {offenders}"
    )


def test_no_flaky_markers_in_p0_suites() -> None:
    """MET-TESTS: zero flaky tests tolerated in P0 — no flaky/rerun markers.

    The taxonomy parks flaky-marked tests under tests/quarantine (inventory
    rule 4); the P0 suites themselves must never carry flaky or rerun markers
    that would let an intermittent failure count as green (§29.3 row 4)."""
    offenders = [
        str(path.relative_to(REPO))
        for path in _suite_test_files()
        if re.search(r"pytest\.mark\.(flaky|randomly)|@flaky|\bflaky\(", path.read_text("utf-8"))
    ]
    assert not offenders, f"flaky/rerun markers are banned in P0 suites: {offenders}"


def test_p0_lanes_run_without_retry_plugins() -> None:
    """MET-TESTS: the P0 lanes cannot mask flakes with automatic retries.

    Zero-flaky tolerance is only real if a flake FAILS the lane: the pinned CI
    toolchain must not ship a rerun plugin, and no workflow lane may pass
    retry flags (--reruns / --force-flaky) to pytest (§29.3 row 4)."""
    requirements = (REPO / "requirements-ci.txt").read_text(encoding="utf-8")
    for banned in ("pytest-rerunfailures", "flaky", "pytest-retry"):
        assert not re.search(rf"^{re.escape(banned)}\b", requirements, flags=re.MULTILINE), (
            f"retry plugin {banned!r} must not be in the pinned CI toolchain"
        )

    addopts = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert "--reruns" not in addopts and "--force-flaky" not in addopts

    for workflow in sorted((REPO / ".github" / "workflows").glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        assert "--reruns" not in text and "--force-flaky" not in text, (
            f"{workflow.name} passes retry flags to a P0 lane"
        )
