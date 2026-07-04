"""Canonical SDD Status Pydantic model and disk-state resolver.

Per ``openspec/changes/agentic-parity-engram-gentle/specs/opencontext-sdd-status/spec.md``:

- ``Status`` carries ``schemaName = "opencontext.sdd-status"`` — a deliberately
  separate namespace from gentle-ai's ``gentle-ai.sdd-status`` (REQ-OSS-001).
- ``Resolve(change, cwd)`` is a pure function over disk state that decides
  ``nextRecommended`` (REQ-OSS-002).
- ``parse_verify_report(path)`` extracts the verdict + failure reasons from
  a verify-report, unicode-aware (REQ-OSS-003).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ArtifactState = Literal["missing", "partial", "done"]
ArtifactStoreMode = Literal["openspec", "engram", "hybrid", "none"]
ApplyState = Literal["idle", "running", "blocked", "done"]


class Status(BaseModel):
    """Canonical SDD status envelope, ``opencontext.sdd-status@1``.

    Owns its own namespace (not a clone of ``gentle-ai.sdd-status``).
    14 top-level fields per REQ-OSS-001.
    """

    model_config = ConfigDict(extra="forbid")

    schemaName: Literal["opencontext.sdd-status"] = "opencontext.sdd-status"
    schemaVersion: Literal[1] = 1
    changeName: str | None = None
    artifactStore: ArtifactStoreMode = "hybrid"
    planningHome: str = "openspec"
    changeRoot: str | None = None
    artifactPaths: dict[str, str] = Field(default_factory=dict)
    artifacts: dict[str, ArtifactState] = Field(default_factory=dict)
    taskProgress: dict[str, int] = Field(default_factory=dict)
    dependencies: dict[str, str] = Field(default_factory=dict)
    applyState: ApplyState = "idle"
    actionContext: dict[str, Any] = Field(default_factory=dict)
    relationships: dict[str, str] = Field(default_factory=dict)
    nextRecommended: str = "select-change"
    blockedReasons: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Resolve — pure function over disk state
# ---------------------------------------------------------------------------


_VERDICT_RE = re.compile(r"^\s*verdict\s*:\s*(\S+)", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*-\s+(.+)$")
_UNICODE_GLYPHS = re.compile(r"[\u2705\u274C\u26A0\uFE0F]")


def parse_verify_report(path: Path) -> tuple[str, list[str]]:
    """Return ``(verdict, failure_reasons)`` from a verify-report.

    Strips unicode marks (``\u2705`` / ``\u274c`` / ``\u26a0\ufe0f``) before
    pattern matching. Missing file or missing ``verdict:`` line → ``("missing", [])``.
    """
    if not path.exists():
        return ("missing", [])
    text = path.read_text(encoding="utf-8")
    text = _UNICODE_GLYPHS.sub("", text)
    match = _VERDICT_RE.search(text)
    if match is None:
        return ("missing", [])
    verdict = match.group(1).strip().upper()
    if verdict == "PASS":
        return ("PASS", [])
    if verdict != "FAIL":
        return (verdict, [])
    # FAIL: collect bullet-list failure lines (any non-header bullet).
    reasons: list[str] = []
    for line in text.splitlines():
        m = _BULLET_RE.match(line)
        if not m:
            continue
        content = m.group(1).strip()
        if not content or content.startswith("#"):
            continue
        reasons.append(content)
    if not reasons:
        reasons.append("(no failure list provided)")
    return ("FAIL", reasons)


def _read_context(cwd: Path) -> dict[str, Any]:
    """Read ``.opencontext/sdd/context.json``; return empty dict on miss."""
    context_path = cwd / ".opencontext" / "sdd" / "context.json"
    if not context_path.exists():
        return {}
    try:
        return dict(json.loads(context_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {}


def _list_changes(changes_root: Path) -> list[str]:
    if not changes_root.exists():
        return []
    return sorted(p.name for p in changes_root.iterdir() if p.is_dir())


def _scan_artifacts(
    change_root: Path, cwd: Path
) -> tuple[dict[str, str], dict[str, ArtifactState], list[str]]:
    """Walk the change dir, return (paths, states, blocked_reasons)."""
    paths: dict[str, str] = {}
    states: dict[str, ArtifactState] = {}
    blocked: list[str] = []

    proposal = change_root / "proposal.md"
    if proposal.exists():
        paths["proposal"] = proposal.relative_to(cwd).as_posix()
        states["proposal"] = "done"
    else:
        states["proposal"] = "missing"
        blocked.append("missing:proposal.md")

    specs_dir = change_root / "specs"
    spec_files = sorted(specs_dir.glob("*/spec.md")) if specs_dir.exists() else []
    if spec_files:
        paths["specs"] = specs_dir.relative_to(cwd).as_posix()
        states["specs"] = "done"
    else:
        states["specs"] = "missing"
        blocked.append("missing:specs/<cap>/spec.md")

    design = change_root / "design.md"
    if design.exists():
        paths["design"] = design.relative_to(cwd).as_posix()
        states["design"] = "done"
    else:
        states["design"] = "missing"
        blocked.append("missing:design.md")

    tasks = change_root / "tasks.md"
    if tasks.exists():
        paths["tasks"] = tasks.relative_to(cwd).as_posix()
        text = tasks.read_text(encoding="utf-8")
        has_unchecked = bool(re.search(r"^\s*-\s\[\s\]", text, re.MULTILINE))
        states["tasks"] = "partial" if has_unchecked else "done"
        if has_unchecked:
            blocked.append("artifact:partial:tasks")
    else:
        states["tasks"] = "missing"
        blocked.append("missing:tasks.md")

    verify = change_root / "verify-report.md"
    if verify.exists():
        paths["verify-report"] = verify.relative_to(cwd).as_posix()
        verdict, reasons = parse_verify_report(verify)
        if verdict == "missing":
            blocked.append("verify_report:missing_verdict_field")
            states["verify-report"] = "partial"
        elif verdict == "PASS":
            states["verify-report"] = "done"
        else:
            states["verify-report"] = "partial"
            for r in reasons:
                blocked.append(f"verify_report:{verdict}:{r}")

    return paths, states, blocked


def _decide_next(
    blocked: list[str],
    artifacts: dict[str, ArtifactState],
    change_root: Path,
) -> tuple[str, ApplyState]:
    """Decision tree (REQ-OSS-002)."""
    if "missing:proposal.md" in blocked:
        return "propose", "idle"
    if any(r.startswith("missing:specs/") for r in blocked):
        return "spec", "idle"
    if "missing:design.md" in blocked:
        return "design", "idle"
    if artifacts.get("tasks") in ("missing", "partial"):
        return "apply", "running"
    # All artifact files present — check verify verdict.
    verdict_block = [r for r in blocked if r.startswith("verify_report:")]
    if verdict_block:
        return "verify", "blocked"
    # Archive only after a passing verify-report exists. Tasks-done with no (or
    # non-passing) verify report routes to verify — a change is never archived
    # unverified (matches the proposal->...->verify->archive DAG).
    if artifacts.get("verify-report") != "done":
        return "verify", "done"
    return "archive", "done"


def Resolve(change: str | None, *, cwd: str) -> Status:
    """Read ``openspec/changes/<change>/`` on disk and decide the next phase.

    Pure function over disk state — no network, no LLM, no global state.
    """
    cwd_path = Path(cwd)
    context = _read_context(cwd_path)
    artifact_store = context.get("artifactStore", "hybrid")
    tdd_mode = context.get("tdd_mode", "ask")
    changes_root = cwd_path / "openspec" / "changes"

    if change is None:
        names = _list_changes(changes_root)
        if len(names) != 1:
            return Status(
                artifactStore=artifact_store,
                actionContext={"tdd_mode": tdd_mode},
                changeName=None,
                nextRecommended="select-change",
                blockedReasons=["ambiguous:select-change"],
            )
        change = names[0]

    change_root = changes_root / change
    if not change_root.exists():
        return Status(
            artifactStore=artifact_store,
            changeName=change,
            actionContext={"tdd_mode": tdd_mode},
            nextRecommended="select-change",
            blockedReasons=[f"missing:changes/{change}"],
        )

    paths, artifacts, blocked = _scan_artifacts(change_root, cwd_path)
    next_rec, apply_state = _decide_next(blocked, artifacts, change_root)

    return Status(
        changeName=change,
        artifactStore=artifact_store,
        changeRoot=change_root.relative_to(cwd_path).as_posix(),
        artifactPaths=paths,
        artifacts=artifacts,
        applyState=apply_state,
        actionContext={"tdd_mode": tdd_mode},
        nextRecommended=next_rec,
        blockedReasons=blocked,
    )


__all__ = [
    "ApplyState",
    "ArtifactState",
    "ArtifactStoreMode",
    "Resolve",
    "Status",
    "parse_verify_report",
]
