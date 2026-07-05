"""``opencontext architecture`` — architecture governance tooling (PROD-005 / B5).

``architecture diff`` snapshots the live versioned contracts and cross-package
dependency edges and diffs them against the frozen baseline
(``tests/architecture/architecture-baseline.json``). It is the human/CI surface over
:mod:`opencontext_core.compat.architecture_diff`:

* ``--json`` emits a pure machine-readable diff to stdout (CI gate);
* the human render uses the brand console.

Exit code is ``0`` when the live state matches the baseline and ``1`` when drift is
detected, so the command doubles as a release gate.

C18 (product-closure-r13): additive ``coverage``, ``gaps``, and ``trace`` subcommands
read real data from ``docs/architecture/54-requirement-to-pr-traceability-matrix.md``
(the authoritative REQ→PR MET/DEFERRED/REJECTED table, 628 lines, parsed at call time).
No fake data — if the matrix file is absent the subcommand exits non-zero with an honest
message.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from opencontext_cli.output import eprint

_DEFAULT_BASELINE = "tests/architecture/architecture-baseline.json"
_TRACEABILITY_MATRIX = "docs/architecture/54-requirement-to-pr-traceability-matrix.md"

# Parses table rows like:
# | **MP-001** Workflow-neutral planning package | ... | MET |
_ROW_RE = re.compile(
    r"^\|\s+\*\*([\w.-]+)\*\*\s+(.*?)\s+\|"  # id + title start
)
_FULL_ROW_RE = re.compile(
    r"^\|\s+\*\*([\w.-]+)\*\*\s+(.*?)\s+\|\s+"  # id + title
    r"`?([^`|]*)`?\s+\|\s+"  # source doc
    r"`?([^`|]*)`?\s+\|\s+"  # pr
    r"`?([^`|]*)`?\s+\|\s+"  # module
    r"([^|]*)\s+\|\s+"  # test
    r"([^|]*)\s+\|\s+"  # benchmark
    r"(MET|DEFERRED|REJECTED)\s+\|"  # status
)


def _resolve_matrix(root: str | None) -> Path:
    """Resolve the traceability matrix relative to root or cwd."""
    base = Path(root) if root else Path.cwd()
    return base / _TRACEABILITY_MATRIX


def _parse_matrix(path: Path) -> list[dict[str, str]]:
    """Parse the traceability matrix into a list of requirement records."""
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _FULL_ROW_RE.match(line)
        if m:
            req_id, title_rest, source, pr, module, test, benchmark, status = m.groups()
            rows.append(
                {
                    "id": req_id.strip(),
                    "title": title_rest.strip(),
                    "source": source.strip(),
                    "pr": pr.strip(),
                    "module": module.strip(),
                    "test": test.strip(),
                    "benchmark": benchmark.strip(),
                    "status": status.strip(),
                }
            )
    return rows


def add_architecture_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    """Register the ADDITIVE ``architecture`` subparser (1.0 CLI surface guard)."""
    arch = subparsers.add_parser("architecture", help="Architecture governance tooling.")
    sub = arch.add_subparsers(dest="architecture_command")

    diff_p = sub.add_parser(
        "diff", help="Diff live contracts/dependencies vs the architecture baseline."
    )
    diff_p.add_argument(
        "--baseline",
        default=None,
        help=f"Path to the architecture baseline JSON (default: {_DEFAULT_BASELINE}).",
    )
    diff_p.add_argument("--json", action="store_true", help="Emit pure JSON to stdout.")

    # C18: coverage / gaps / trace subcommands.
    cov_p = sub.add_parser(
        "coverage",
        help="Show MET/DEFERRED/REJECTED totals from the requirement traceability matrix.",
    )
    cov_p.add_argument("--json", action="store_true", help="Emit pure JSON to stdout.")
    cov_p.add_argument("--root", default=None, help="Repository root (default: cwd).")

    gaps_p = sub.add_parser(
        "gaps",
        help="List requirements that are not yet MET (DEFERRED or REJECTED).",
    )
    gaps_p.add_argument("--json", action="store_true", help="Emit pure JSON to stdout.")
    gaps_p.add_argument("--root", default=None, help="Repository root (default: cwd).")
    gaps_p.add_argument(
        "--status",
        default="DEFERRED",
        choices=["DEFERRED", "REJECTED", "ALL"],
        help="Filter by status (default: DEFERRED).",
    )

    trace_p = sub.add_parser(
        "trace",
        help="Trace a single requirement ID through the matrix.",
    )
    trace_p.add_argument("req_id", help="Requirement ID to trace (e.g. MP-001).")
    trace_p.add_argument("--json", action="store_true", help="Emit pure JSON to stdout.")
    trace_p.add_argument("--root", default=None, help="Repository root (default: cwd).")


def handle_architecture(args: argparse.Namespace) -> int:
    cmd = getattr(args, "architecture_command", None)
    if cmd == "diff":
        return _handle_diff(args)
    if cmd == "coverage":
        return _handle_coverage(args)
    if cmd == "gaps":
        return _handle_gaps(args)
    if cmd == "trace":
        return _handle_trace(args)
    eprint(
        "Usage: opencontext architecture <diff|coverage|gaps|trace> [options]\n"
        "  diff      Diff live contracts vs baseline\n"
        "  coverage  Show MET/DEFERRED/REJECTED totals\n"
        "  gaps      List DEFERRED requirements\n"
        "  trace     Trace a single requirement ID"
    )
    return 1


def _resolve_baseline(args: argparse.Namespace) -> Path:
    raw = getattr(args, "baseline", None)
    return Path(raw) if raw else Path.cwd() / _DEFAULT_BASELINE


def _handle_coverage(args: argparse.Namespace) -> int:
    """Emit MET/DEFERRED/REJECTED totals from the traceability matrix."""
    matrix_path = _resolve_matrix(getattr(args, "root", None))
    if not matrix_path.is_file():
        eprint(f"Traceability matrix not found: {matrix_path}")
        return 2

    rows = _parse_matrix(matrix_path)
    if not rows:
        eprint(f"No requirement rows parsed from {matrix_path}")
        return 2

    by_status: dict[str, int] = {}
    for row in rows:
        s = row["status"]
        by_status[s] = by_status.get(s, 0) + 1

    met = by_status.get("MET", 0)
    deferred = by_status.get("DEFERRED", 0)
    rejected = by_status.get("REJECTED", 0)
    total = len(rows)

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "met": met,
                    "deferred": deferred,
                    "rejected": rejected,
                    "total": total,
                    "coverage_pct": round(met / total * 100, 1) if total else 0.0,
                },
                indent=2,
            )
        )
        return 0

    try:
        from opencontext_core.dx.console_styles import console

        console.header("Architecture Coverage")
        console.print(f"[dim]source: {matrix_path}[/]")
        console.print(f"  MET      : {met}")
        console.print(f"  DEFERRED : {deferred}")
        console.print(f"  REJECTED : {rejected}")
        console.print(f"  Total    : {total}")
        pct = round(met / total * 100, 1) if total else 0.0
        console.print(f"  Coverage : {pct}%")
    except Exception:
        print(f"MET: {met} / DEFERRED: {deferred} / REJECTED: {rejected} / Total: {total}")
    return 0


def _handle_gaps(args: argparse.Namespace) -> int:
    """List requirements that are not yet MET."""
    matrix_path = _resolve_matrix(getattr(args, "root", None))
    if not matrix_path.is_file():
        eprint(f"Traceability matrix not found: {matrix_path}")
        return 2

    rows = _parse_matrix(matrix_path)
    status_filter = getattr(args, "status", "DEFERRED")
    if status_filter == "ALL":
        gaps = [r for r in rows if r["status"] != "MET"]
    else:
        gaps = [r for r in rows if r["status"] == status_filter]

    if getattr(args, "json", False):
        print(json.dumps(gaps, indent=2))
        return 0

    try:
        from opencontext_core.dx.console_styles import console

        console.header(f"Architecture Gaps ({status_filter})")
        console.print(f"[dim]source: {matrix_path}[/]")
        for gap in gaps:
            console.print(f"  [{gap['status']}] {gap['id']} — {gap['title'][:80]}")
    except Exception:
        for gap in gaps:
            print(f"[{gap['status']}] {gap['id']} — {gap['title'][:80]}")
    return 0


def _handle_trace(args: argparse.Namespace) -> int:
    """Trace a single requirement ID through the matrix."""
    req_id: str = args.req_id
    matrix_path = _resolve_matrix(getattr(args, "root", None))
    if not matrix_path.is_file():
        eprint(f"Traceability matrix not found: {matrix_path}")
        return 2

    rows = _parse_matrix(matrix_path)
    matches = [r for r in rows if r["id"].upper() == req_id.upper()]

    if not matches:
        eprint(f"Requirement {req_id!r} not found in {matrix_path}")
        return 1

    row = matches[0]
    if getattr(args, "json", False):
        print(json.dumps(row, indent=2))
        return 0

    try:
        from opencontext_core.dx.console_styles import console

        console.header(f"Requirement: {row['id']}")
        console.print(f"  Title    : {row['title']}")
        console.print(f"  Status   : {row['status']}")
        console.print(f"  PR       : {row['pr']}")
        console.print(f"  Module   : {row['module']}")
        console.print(f"  Test     : {row['test']}")
        console.print(f"  Source   : {row['source']}")
    except Exception:
        for k, v in row.items():
            print(f"  {k}: {v}")
    return 0


def _handle_diff(args: argparse.Namespace) -> int:
    from opencontext_core.compat.architecture_diff import current_snapshot, diff, load_baseline

    baseline_path = _resolve_baseline(args)
    if not baseline_path.is_file():
        eprint(f"Architecture baseline not found: {baseline_path}")
        return 2

    result = diff(load_baseline(baseline_path), current_snapshot())

    if getattr(args, "json", False):
        payload = {**result.model_dump(), "drift": result.has_drift}
        print(json.dumps(payload, indent=2, sort_keys=True))  # pure JSON to stdout
        return 1 if result.has_drift else 0

    _render_human(result, baseline_path)
    return 1 if result.has_drift else 0


def _render_human(result: Any, baseline_path: Path) -> None:
    from opencontext_core.dx.console_styles import console

    console.header("Architecture Diff")
    console.print(f"[dim]baseline: {baseline_path}[/]")
    if not result.has_drift:
        console.success("No architecture drift — live contracts and dependencies match baseline.")
        return

    sections = (
        ("Added contracts", result.added_contracts),
        ("Removed contracts", result.removed_contracts),
        ("Changed contracts", result.changed_contracts),
        ("Added dependencies", result.added_dependencies),
        ("Removed dependencies", result.removed_dependencies),
    )
    for title, items in sections:
        if not items:
            continue
        console.section(title)
        for item in items:
            console.print(f"  - {item}")
    console.warning(
        "Architecture drift detected — bump the affected schema_version(s) and "
        "regenerate architecture-baseline.json in the same change."
    )
