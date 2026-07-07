"""SDD review phase — honest structural review over a change's artifacts + diff.

Reuses the status resolver's artifact scan (the same disk truth ``sdd status``
reports) plus a best-effort git diff footprint. Without an executor/model this
never fabricates findings: the persisted report is marked ``mode: structural``
and only carries checks a static pass can prove (artifact presence and
completeness, verify verdict, diff summary). Model-backed multi-perspective
review remains ``opencontext review`` (party mode).
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opencontext_sdd.runner import PhaseResultEnvelope
from opencontext_sdd.status import Resolve, Status

REVIEW_REPORT_FILENAME = "review-report.json"

# Core planning artifacts a review expects to be complete, mapped to how loud
# the structural finding is when they are not.
_SEVERITY_BY_STATE = {"missing": "high", "partial": "medium"}
_REVIEWED_ARTIFACTS = ("proposal", "specs", "design", "tasks")


def _diff_summary(cwd: Path) -> dict[str, Any]:
    """Best-effort working-tree diff footprint via git; honest on failure."""
    unavailable = {"available": False, "files_changed": 0, "insertions": 0, "deletions": 0}
    try:
        proc = subprocess.run(
            ["git", "diff", "--numstat", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return unavailable
    if proc.returncode != 0:
        return unavailable
    files = insertions = deletions = 0
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        files += 1
        insertions += int(parts[0]) if parts[0].isdigit() else 0
        deletions += int(parts[1]) if parts[1].isdigit() else 0
    return {
        "available": True,
        "files_changed": files,
        "insertions": insertions,
        "deletions": deletions,
    }


def _structural_findings(status: Status) -> list[dict[str, str]]:
    """Findings a static pass can prove: incomplete artifacts, failing verify."""
    findings: list[dict[str, str]] = []
    for name in _REVIEWED_ARTIFACTS:
        state = status.artifacts.get(name, "missing")
        severity = _SEVERITY_BY_STATE.get(state)
        if severity is None:
            continue
        findings.append(
            {
                "severity": severity,
                "title": f"{name} artifact is {state}",
                "details": f"The '{name}' artifact must be complete before archive; "
                f"current state: {state}.",
            }
        )
    for reason in status.blockedReasons:
        if reason.startswith("verify_report:"):
            findings.append(
                {
                    "severity": "high",
                    "title": "verify report is not passing",
                    "details": reason,
                }
            )
    return findings


def run_review(change: str | None, *, cwd: str) -> PhaseResultEnvelope:
    """Structural review of *change*; persists ``review-report.json`` in the change dir.

    Returns the canonical phase envelope. A missing change dir returns a
    ``blocked`` envelope and writes nothing.
    """
    cwd_path = Path(cwd)
    status = Resolve(change, cwd=str(cwd_path))
    if status.changeRoot is None:
        return PhaseResultEnvelope(
            status="blocked",
            executive_summary=(
                f"No SDD change artifacts found for '{change or '(unselected)'}' — "
                "nothing to review."
            ),
            artifacts={},
            next_recommended=status.nextRecommended,
            risks=list(status.blockedReasons),
            skill_resolution="none",
            phase="review",
            trace_id="",
        )

    findings = _structural_findings(status)
    report: dict[str, Any] = {
        "schemaName": "opencontext.sdd-review",
        "schemaVersion": 1,
        "change": status.changeName,
        "mode": "structural",
        "status": "ok",
        "artifacts": dict(status.artifacts),
        "findings": findings,
        "diff": _diff_summary(cwd_path),
        "next_recommended": status.nextRecommended,
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }
    report_path = cwd_path / status.changeRoot / REVIEW_REPORT_FILENAME
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    return PhaseResultEnvelope(
        status="ok",
        executive_summary=(
            f"Structural review of '{status.changeName}': {len(findings)} finding(s). "
            "No executor/model configured — static checks only."
        ),
        artifacts={"review-report": report_path.relative_to(cwd_path).as_posix()},
        next_recommended=status.nextRecommended,
        risks=[f"{f['severity']}:{f['title']}" for f in findings],
        skill_resolution="none",
        phase="review",
        trace_id="",
    )


__all__ = ["REVIEW_REPORT_FILENAME", "run_review"]
