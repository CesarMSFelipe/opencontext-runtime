"""OC Flow run bundle: gate evaluation, status enforcement, evidence writer.

Persists the harness-style run manifest (``run.json`` + ``gates.json`` +
``verification.json`` + ``mutations.diff``) for OC Flow runs so the
RUN_STATE_CONTRACT evidence rules hold for both workflows. Gate evaluation and
final-status enforcement are pure functions; the writer is a lean file dumper.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GATE_PASSED = "passed"
GATE_FAILED = "failed"
GATE_SKIPPED = "skipped"

#: Gate ids evaluated for every OC Flow run (order is the persisted order).
OC_FLOW_GATE_IDS = (
    "workspace_valid",
    "config_valid",
    "context_pack_created",
    "executor_available",
    "tdd_red_proven_if_strict",
    "mutation_performed_if_required",
    "verification_executed",
    "verification_passed",
    "report_written",
)

_GATE_MESSAGES = {
    "workspace_valid": ("workspace root exists", "workspace root is missing or invalid"),
    "config_valid": ("project config loaded", "project config failed to load"),
    "context_pack_created": ("context envelope assembled", "no context envelope produced"),
    "executor_available": (
        "a productive executor was available",
        "no productive executor/provider configured",
    ),
    "tdd_red_proven_if_strict": (
        "strict TDD: RED proven before mutation",
        "strict TDD: RED not proven before mutation",
    ),
    "mutation_performed_if_required": (
        "mutation task produced edits",
        "mutation task produced no edits",
    ),
    "verification_executed": (
        "verification command executed",
        "verification never executed",
    ),
    "verification_passed": ("verification passed", "verification failed"),
    "report_written": ("run report persisted", "run report not persisted"),
}


def _gate(gate_id: str, value: bool | None) -> dict[str, Any]:
    if value is None:
        return {
            "id": gate_id,
            "phase": "oc-flow",
            "status": GATE_SKIPPED,
            "message": "not applicable to this run",
        }
    ok_msg, fail_msg = _GATE_MESSAGES[gate_id]
    return {
        "id": gate_id,
        "phase": "oc-flow",
        "status": GATE_PASSED if value else GATE_FAILED,
        "message": ok_msg if value else fail_msg,
    }


def evaluate_oc_flow_gates(
    *,
    workspace_valid: bool,
    config_valid: bool,
    context_pack_created: bool | None,
    executor_available: bool | None,
    tdd_red_proven_if_strict: bool | None,
    mutation_performed_if_required: bool | None,
    verification_executed: bool | None,
    verification_passed: bool | None,
    report_written: bool = True,
) -> list[dict[str, Any]]:
    """Evaluate the OC Flow gate catalog. ``None`` inputs are skipped gates."""
    return [
        _gate("workspace_valid", workspace_valid),
        _gate("config_valid", config_valid),
        _gate("context_pack_created", context_pack_created),
        _gate("executor_available", executor_available),
        _gate("tdd_red_proven_if_strict", tdd_red_proven_if_strict),
        _gate("mutation_performed_if_required", mutation_performed_if_required),
        _gate("verification_executed", verification_executed),
        _gate("verification_passed", verification_passed),
        _gate("report_written", report_written),
    ]


def enforce_gates(status: str, gates: list[dict[str, Any]]) -> str:
    """The ONE enforcement point: no `completed`/`passed` with a failed gate.

    Non-success statuses already tell the truth and pass through unchanged.
    """
    if status not in ("completed", "passed"):
        return status
    if any(g.get("status") == GATE_FAILED for g in gates):
        return "blocked"
    return status


def write_run_bundle(
    run_dir: Path,
    *,
    manifest: dict[str, Any],
    gates: list[dict[str, Any]],
    verification: dict[str, Any],
    patch_text: str | None = None,
) -> None:
    """Persist run.json / gates.json / verification.json (+ mutations.diff)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    _dump(run_dir / "run.json", manifest)
    _dump(run_dir / "gates.json", {"gates": gates})
    _dump(run_dir / "verification.json", verification)
    if patch_text and patch_text.strip() and not patch_text.lstrip().startswith("#"):
        # Bytes + LF-normalized so the unified diff stays portable (same rule as
        # the artifacts/oc-flow/patch.diff writer).
        normalized = patch_text.replace("\r\n", "\n").replace("\r", "\n")
        (run_dir / "mutations.diff").write_bytes(normalized.encode("utf-8", errors="replace"))


def _dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
