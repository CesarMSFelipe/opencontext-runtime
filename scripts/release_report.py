#!/usr/bin/env python3
"""Compose the machine-readable release report (RELEASE_CONTRACT.md).

Aggregates the release-gate stage results — artifact checksums, hygiene audit,
fresh-venv acceptance run, uninstall-verify — into
``artifacts/release-report.json``. The acceptance numbers are parsed from the
pytest log of the gate run, never invented.

Usage:
    python scripts/release_report.py \
        --version 1.7.0 \
        --artifact dist/opencontext.pyz --artifact packages/*/dist/*.whl \
        --hygiene-exit 0 \
        --acceptance-log /tmp/acceptance.log --acceptance-oc-bin <path> \
        --uninstall-exit 0 \
        [--limitation "text"] [--output artifacts/release-report.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_SUMMARY_TOKEN = re.compile(r"(\d+) (passed|failed|xfailed|xpassed|errors?|skipped|warnings?)\b")
_GAP_ID = re.compile(r"GAP-[A-Za-z0-9]+")


def parse_pytest_summary(log: str) -> dict[str, int] | None:
    """Parse the final pytest summary line into passed/failed/xfailed counts.

    Errors count as failures; warnings/skips/xpasses are not gate outcomes.
    Returns None when the log has no summary line (e.g. ``-qq`` output).
    """
    counts: dict[str, int] | None = None
    for line in log.splitlines():
        if " in " not in line:
            continue
        tokens = _SUMMARY_TOKEN.findall(line)
        outcomes = {kind for _, kind in tokens}
        if not outcomes & {"passed", "failed", "xfailed", "error", "errors"}:
            continue
        parsed = {"passed": 0, "failed": 0, "xfailed": 0}
        for count, kind in tokens:
            if kind in ("error", "errors"):
                parsed["failed"] += int(count)
            elif kind in parsed:
                parsed[kind] = int(count)
        counts = parsed
    return counts


def collect_gap_ids(log: str) -> list[str]:
    """Collect the GAP ids of still-open xfails from an acceptance log."""
    gaps: set[str] = set()
    for line in log.splitlines():
        if "XFAIL" not in line:
            continue
        gaps.update(_GAP_ID.findall(line))
    return sorted(gaps)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--artifact", action="append", type=Path, default=[], required=True)
    parser.add_argument("--hygiene-exit", type=int, required=True)
    parser.add_argument("--acceptance-log", type=Path, required=True)
    parser.add_argument("--acceptance-oc-bin", default=None)
    parser.add_argument("--uninstall-exit", type=int, required=True)
    parser.add_argument("--limitation", action="append", default=[])
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "release-report.json")
    args = parser.parse_args(argv)

    missing = [p for p in args.artifact if not p.is_file()]
    if missing:
        print(f"missing artifacts: {missing}", file=sys.stderr)
        return 2
    log_text = args.acceptance_log.read_text(encoding="utf-8", errors="replace")
    summary = parse_pytest_summary(log_text)
    if summary is None:
        print(f"no pytest summary line found in {args.acceptance_log}", file=sys.stderr)
        return 2
    remaining_gaps = collect_gap_ids(log_text)

    report = {
        "version": args.version,
        "generated_at": datetime.now(UTC).isoformat(),
        "artifacts": [{"name": p.name, "sha256": _sha256(p)} for p in args.artifact],
        "hygiene": "pass" if args.hygiene_exit == 0 else "fail",
        "acceptance": {
            "passed": summary["passed"],
            "xfailed": summary["xfailed"],
            "failed": summary["failed"],
            "remaining_gaps": remaining_gaps,
            "oc_bin": args.acceptance_oc_bin,
        },
        "uninstall_verify": "pass" if args.uninstall_exit == 0 else "fail",
        "known_limitations": [*remaining_gaps, *args.limitation],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")

    gate_ok = args.hygiene_exit == 0 and args.uninstall_exit == 0 and summary["failed"] == 0
    return 0 if gate_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
