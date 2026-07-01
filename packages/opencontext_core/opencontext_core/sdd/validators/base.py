"""Tiny SDD phase artifact validators."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PhaseValidationResult:
    passed: bool
    reason: str = ""


def validate_phase(phase: str, content: str) -> PhaseValidationResult:
    text = (content or "").strip()
    if not text or text.lower() == "ok":
        return PhaseValidationResult(False, "phase output failed contract validation")
    validators = {
        "explore": _has_any("context", "files", "symbols", "unknown"),
        "propose": _has_all("intent", "scope", "risk"),
        "proposal": _has_all("intent", "scope", "risk"),
        "spec": _valid_spec,
        "design": _has_all("approach", "module", "data flow", "risk", "rollback"),
        "tasks": _valid_tasks,
        "apply": _has_any("applyedit", "patch", "planned", "planned_only"),
        "verify": _has_all("command", "outcome"),
        "review": _has_all("finding", "severity"),
        "archive": _has_all("status", "artifact"),
    }
    result: PhaseValidationResult = validators.get(phase, _valid_nonempty)(text)
    return result


def _valid_nonempty(text: str) -> PhaseValidationResult:
    if bool(text):
        return PhaseValidationResult(True, "")
    return PhaseValidationResult(False, "phase output failed contract validation")


def _has_any(*needles: str) -> Any:
    def check(text: str) -> PhaseValidationResult:
        low = text.lower()
        ok = any(n in low for n in needles)
        return PhaseValidationResult(
            ok, "phase output failed contract validation" if not ok else ""
        )

    return check


def _has_all(*needles: str) -> Any:
    def check(text: str) -> PhaseValidationResult:
        low = text.lower()
        ok = all(n in low for n in needles)
        return PhaseValidationResult(
            ok, "phase output failed contract validation" if not ok else ""
        )

    return check


def _valid_spec(text: str) -> PhaseValidationResult:
    low = text.lower()
    ok = ("must" in low or "shall" in low) and all(w in low for w in ("given", "when", "then"))
    return PhaseValidationResult(ok, "phase output failed contract validation" if not ok else "")


def _valid_tasks(text: str) -> PhaseValidationResult:
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        data = None
    tasks = data.get("tasks") if isinstance(data, dict) else data
    if not isinstance(tasks, list) or not tasks:
        return PhaseValidationResult(False, "phase output failed contract validation")
    for task in tasks:
        if not isinstance(task, dict):
            return PhaseValidationResult(False, "phase output failed contract validation")
        if not (task.get("id") and task.get("description")):
            return PhaseValidationResult(False, "phase output failed contract validation")
        # Each task must have a file/verification mapping so it is actionable.
        # Accept any of: file_paths, files, verification, acceptance_criteria.
        has_file_map = bool(
            task.get("file_paths")
            or task.get("files")
            or task.get("verification")
            or task.get("acceptance_criteria")
        )
        if not has_file_map:
            return PhaseValidationResult(False, "phase output failed contract validation")
    return PhaseValidationResult(True)
