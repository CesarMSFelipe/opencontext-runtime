"""Static test inventory + suite taxonomy (plan §26.1/§26.2).

Walks ``tests/`` WITHOUT importing or running any test and emits
``artifacts/test-inventory.json`` + ``artifacts/test-inventory.md``:
per test file it records path, suite (top-level dir under ``tests/``),
static test count (``def test_`` occurrences), pytest markers used,
mock imports, filesystem/subprocess usage heuristics, requirement/bug
IDs, and a classification SUGGESTION. Nothing here deletes or modifies
tests — candidates are recommendations for a later, human-reviewed pass
(plan §26.3).

Classification rules (transparent, applied in this precedence order):

1.  suite ``acceptance``            -> KEEP_ACCEPTANCE (black-box contract
    suite, ACCEPTANCE_CONTRACT.md AC-001..AC-030).
2.  suite ``golden`` or ``compat``  -> KEEP_CONTRACT (snapshot/compat
    surfaces are contract tests by construction).
3.  suite ``done_in_v1`` or ``quarantine`` -> QUARANTINE (archived v1
    validation suite / already-quarantined skip-marked files).
4.  ``flaky`` marker present        -> QUARANTINE (fix or expire per §26.3).
5.  mock imports AND no filesystem AND no subprocess usage -> DELETE
    candidate ("only proves mocks" rule from §26.3).
6.  suite ``e2e``/``integration``/``mcp``/``environment`` ->
    KEEP_INTEGRATION_BOUNDARY.
7.  requirement/bug ID in the body (``GAP-``/``AC-``/``REQ-``/``BUG-``
    followed by digits) or ``regression`` in the filename ->
    KEEP_REGRESSION.
8.  no mock, no filesystem, no subprocess (pure logic) ->
    KEEP_UNIT_CRITICAL.
9.  everything else (touches real fs/subprocess from a misc suite) ->
    KEEP_INTEGRATION_BOUNDARY.

Second pass: files sharing a normalized stem (``test_pack.py`` in two
suites) are MERGE candidates — but only when their base classification is
KEEP_UNIT_CRITICAL or KEEP_INTEGRATION_BOUNDARY; acceptance/contract/
regression/quarantine/delete outcomes are never downgraded to MERGE
(§26.3: keep the most external or clearest duplicate).

Heuristics (static string/regex scans, so they are cheap and auditable):

- test count:      lines matching ``def test_`` / ``async def test_``.
- markers:         every ``pytest.mark.<name>`` occurrence.
- mock usage:      import lines for ``unittest.mock`` / ``mock``.
- filesystem:      ``tmp_path``/``tmpdir`` fixtures, ``open(``,
                   ``write_text(``/``write_bytes(``.
- subprocess:      any ``subprocess`` reference.

Usage:

    python scripts/test_inventory.py [--tests-root tests] [--out artifacts]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

CLASSIFICATIONS = (
    "KEEP_ACCEPTANCE",
    "KEEP_CONTRACT",
    "KEEP_UNIT_CRITICAL",
    "KEEP_INTEGRATION_BOUNDARY",
    "KEEP_REGRESSION",
    "MERGE",
    "DELETE",
    "QUARANTINE",
)

CONTRACT_SUITES = {"golden", "compat"}
BOUNDARY_SUITES = {"e2e", "integration", "mcp", "environment"}
QUARANTINE_SUITES = {"done_in_v1", "quarantine"}
# MERGE may only replace these base labels (never acceptance/contract/etc.).
MERGEABLE = {"KEEP_UNIT_CRITICAL", "KEEP_INTEGRATION_BOUNDARY"}
# Directories never inventoried: fixture projects contain seeded failing
# tests (see tests/acceptance/conftest.py collect_ignore_glob).
SKIP_DIRS = {"fixtures", "__pycache__"}

_TEST_DEF_RE = re.compile(r"^\s*(?:async\s+)?def (test_\w+)", re.MULTILINE)
_MARKER_RE = re.compile(r"pytest\.mark\.(\w+)")
_MOCK_IMPORT_RE = re.compile(
    r"^\s*(?:from unittest\.mock import|from unittest import mock\b"
    r"|import unittest\.mock\b|from mock import|import mock\b)",
    re.MULTILINE,
)
_FILESYSTEM_RE = re.compile(r"\btmp_path\b|\btmpdir\b|\bopen\(|\.write_text\(|\.write_bytes\(")
_SUBPROCESS_RE = re.compile(r"\bsubprocess\b")
_REQUIREMENT_ID_RE = re.compile(r"\b(?:GAP|AC|REQ|BUG)-\d+\b")


def analyze_source(rel_path: str, source: str) -> dict:
    """Build the static record for one test file (pure: path + text in)."""
    parts = Path(rel_path).parts
    suite = parts[1] if len(parts) > 2 else "(root)"
    return {
        "path": Path(rel_path).as_posix(),
        "suite": suite,
        "test_count": len(_TEST_DEF_RE.findall(source)),
        "markers": sorted(set(_MARKER_RE.findall(source))),
        "uses_mock": bool(_MOCK_IMPORT_RE.search(source)),
        "uses_filesystem": bool(_FILESYSTEM_RE.search(source)),
        "uses_subprocess": bool(_SUBPROCESS_RE.search(source)),
        "requirement_ids": sorted(set(_REQUIREMENT_ID_RE.findall(source))),
    }


def classify(record: dict) -> tuple[str, list[str]]:
    """Apply the docstring's precedence rules; returns (label, reasons)."""
    suite = record["suite"]
    if suite == "acceptance":
        return "KEEP_ACCEPTANCE", ["rule 1: tests/acceptance black-box suite"]
    if suite in CONTRACT_SUITES:
        return "KEEP_CONTRACT", [f"rule 2: contract suite '{suite}'"]
    if suite in QUARANTINE_SUITES:
        return "QUARANTINE", [f"rule 3: archived/quarantined suite '{suite}'"]
    if "flaky" in record["markers"]:
        return "QUARANTINE", ["rule 4: flaky marker"]
    if record["uses_mock"] and not record["uses_filesystem"] and not record["uses_subprocess"]:
        return "DELETE", ["rule 5: mock-only file (no real fs/subprocess touched)"]
    if suite in BOUNDARY_SUITES:
        return "KEEP_INTEGRATION_BOUNDARY", [f"rule 6: boundary suite '{suite}'"]
    if record.get("requirement_ids") or "regression" in Path(record["path"]).name:
        return "KEEP_REGRESSION", ["rule 7: requirement/bug ID or regression filename"]
    if not record["uses_mock"] and not record["uses_filesystem"] and not record["uses_subprocess"]:
        return "KEEP_UNIT_CRITICAL", ["rule 8: pure logic (no mock/fs/subprocess)"]
    return "KEEP_INTEGRATION_BOUNDARY", ["rule 9: touches real fs/subprocess"]


def normalized_stem(path: str) -> str:
    """``tests/unit/test_pack.py`` -> ``pack`` (duplicate-stem grouping key)."""
    stem = Path(path).stem
    return stem.removeprefix("test_").removesuffix("_test")


def apply_merge_pass(records: list[dict]) -> None:
    """Mark duplicate-stem files as MERGE candidates (mergeable labels only)."""
    by_stem: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_stem[normalized_stem(record["path"])].append(record)
    for stem, group in by_stem.items():
        if len(group) < 2:
            continue
        peers = ", ".join(sorted(r["path"] for r in group))
        for record in group:
            if record["classification"] in MERGEABLE:
                record["classification"] = "MERGE"
                record["reasons"] = [f"merge pass: stem '{stem}' shared by {peers}"]


def build_inventory(tests_root: Path) -> dict:
    """Walk ``tests_root`` and produce the full classified inventory."""
    records = []
    for path in sorted(tests_root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        name = path.name
        if not (name.startswith("test_") or name.endswith("_test.py")):
            continue
        rel = path.relative_to(tests_root.parent).as_posix()
        record = analyze_source(rel, path.read_text(encoding="utf-8", errors="replace"))
        record["classification"], record["reasons"] = classify(record)
        records.append(record)
    apply_merge_pass(records)
    return {
        "total_files": len(records),
        "total_tests": sum(r["test_count"] for r in records),
        "classification_totals": dict(Counter(r["classification"] for r in records)),
        "files": records,
    }


def render_markdown(inventory: dict) -> str:
    """Human summary: per-suite table + DELETE/MERGE candidate lists."""
    records = inventory["files"]
    suites: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        suites[record["suite"]].append(record)

    lines = [
        "# Test inventory (plan §26.1/§26.2)",
        "",
        "Generated by `python scripts/test_inventory.py` — static scan, no",
        "tests executed. Classifications are SUGGESTIONS ONLY (§26.3 requires",
        "a human-reviewed pass before any deletion).",
        "",
        f"- Test files: **{inventory['total_files']}**",
        f"- Test functions (static `def test_` count): **{inventory['total_tests']}**",
        "",
        "## Per-suite summary",
        "",
        "| Suite | Files | Tests | Top classification |",
        "|-------|-------|-------|--------------------|",
    ]
    for suite in sorted(suites):
        group = suites[suite]
        top = Counter(r["classification"] for r in group).most_common(1)[0][0]
        tests = sum(r["test_count"] for r in group)
        lines.append(f"| {suite} | {len(group)} | {tests} | {top} |")

    lines += ["", "## Classification totals", ""]
    totals = Counter(r["classification"] for r in records)
    for label in CLASSIFICATIONS:
        lines.append(f"- {label}: {totals.get(label, 0)}")

    for label, title in (("DELETE", "DELETE candidates"), ("MERGE", "MERGE candidates")):
        lines += ["", f"## {title}", ""]
        candidates = [r for r in records if r["classification"] == label]
        if not candidates:
            lines.append("(none)")
        for record in candidates:
            lines.append(f"- `{record['path']}` — {record['reasons'][0]}")

    lines += ["", "## QUARANTINE", ""]
    quarantined = [r for r in records if r["classification"] == "QUARANTINE"]
    if not quarantined:
        lines.append("(none)")
    for record in quarantined:
        lines.append(f"- `{record['path']}` — {record['reasons'][0]}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tests-root", default="tests", type=Path)
    parser.add_argument("--out", default="artifacts", type=Path)
    args = parser.parse_args()

    inventory = build_inventory(args.tests_root)
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "test-inventory.json"
    md_path = args.out / "test-inventory.md"
    json_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(inventory), encoding="utf-8")
    print(f"wrote {json_path} and {md_path}")
    print(
        f"{inventory['total_files']} files, {inventory['total_tests']} tests, "
        f"totals: {inventory['classification_totals']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
