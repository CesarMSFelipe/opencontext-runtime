"""Interactive agentic loop — SDD workflow with user checkpoints."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console

FLOWS = {
    "quick": "quick",
    "standard": "standard",
    "full": "sdd",
    "autonomous": "sdd",
    "quality": "full+quality",
    "judgment": "full+judgment",
    "gga": "full+gga",
}

COMPRESSION_MODES = ["terse", "compact", "efficient", "none"]


def add_loop_commands(subparsers: argparse._SubParsersAction[Any]) -> None:
    loop = subparsers.add_parser(
        "loop",
        help="Interactive agentic workflow loop with user checkpoints.",
    )
    loop.add_argument("--task", "-t", required=True, help="Task description")
    loop.add_argument(
        "--flow",
        choices=list(FLOWS.keys()),
        default="full",
        help="Workflow track: quick/standard/full/autonomous/quality/judgment/gga",
    )
    loop.add_argument(
        "--compress",
        choices=COMPRESSION_MODES,
        default="efficient",
        help="Compression mode for agent output (default: efficient)",
    )
    loop.add_argument(
        "--root",
        default=".",
        help="Project root directory",
    )
    loop.add_argument(
        "--max-rounds",
        type=int,
        default=1,
        help="Max loop iterations (>1 = retry on failure)",
    )
    loop.add_argument(
        "--autonomous",
        action="store_true",
        help="Skip user prompts — gates decide (same as --flow autonomous)",
    )
    loop.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan phases but do not execute",
    )


def handle_loop(args: argparse.Namespace, config: object = None) -> int:
    """Run the interactive agentic loop."""
    flow = "autonomous" if getattr(args, "autonomous", False) else getattr(args, "flow", "full")
    task = args.task
    root = Path(getattr(args, "root", "."))
    compress_mode = getattr(args, "compress", "efficient")
    max_rounds = getattr(args, "max_rounds", 1)
    dry_run = getattr(args, "dry_run", False)
    autonomous = flow == "autonomous"

    workflow = FLOWS.get(flow, "sdd")

    _print_header(task, flow, compress_mode)

    if dry_run:
        try:
            from opencontext_core.harness.runner import HarnessRunner

            runner = HarnessRunner(root=root)
            phases = runner.schedule_phases(workflow)
        except Exception:
            phases = []
        console.print()
        console.info("Dry run — phases that would execute:")
        for p in phases:
            console.print(f"  - {p.upper()}")
        return 0

    manifest_path = root / ".storage" / "opencontext" / "project_manifest.json"
    if not manifest_path.exists():
        eprint("No index found. Run 'opencontext index .' first, then retry.")
        return 1

    try:
        from opencontext_core.backends.factory import BackendFactory

        compressor = BackendFactory.create_compression_backend(compress_mode)
    except Exception:
        compressor = None

    for round_num in range(1, max_rounds + 1):
        if max_rounds > 1:
            console.section(f"Round {round_num}/{max_rounds}")

        success = _run_loop(task, workflow, root, config, compressor, autonomous)
        if success:
            break
        if round_num < max_rounds:
            console.warning(f"Round {round_num} incomplete. Retrying...")
        else:
            eprint(f"Loop did not complete after {max_rounds} round(s).")
            return 1

    return 0


def _run_loop(
    task: str,
    workflow: str,
    root: Path,
    config: object,
    compressor: Any,
    autonomous: bool,
) -> bool:
    """Execute one loop iteration. Returns True if all phases completed."""
    try:
        from opencontext_core.harness.runner import HarnessRunner
    except ImportError as e:
        eprint(f"Runtime not available: {e}")
        return False

    runner = HarnessRunner(root=root)

    try:
        result = runner.run(workflow, task)
    except Exception as e:
        eprint(f"error: {e}")
        return False

    _print_run_summary(result)
    status = getattr(result, "status", None)
    passed = status is not None and getattr(status, "value", str(status)) in ("passed", "warning")
    if passed:
        console.success("Loop complete.")
    elif not passed:
        console.warning("Loop did not complete — check warnings above.")
    return passed


def _print_header(task: str, flow: str, compress: str) -> None:
    console.header("OpenContext Loop")
    console.dim(f"flow: {flow}  ·  compress: {compress}")
    console.dim(f"task: {task}")


def _print_run_summary(result: Any) -> None:
    """Print a human-readable run summary with per-phase breakdown."""
    if result is None:
        console.dim("  no result")
        return

    ledgers = getattr(result, "ledgers", [])
    artifacts = getattr(result, "artifacts", [])
    warnings = getattr(result, "warnings", [])
    gates = getattr(result, "gates", [])
    status: Any = getattr(result, "status", None)
    status_str = status.value if hasattr(status, "value") else str(status)

    # Per-phase summary
    artifacts_by_phase: dict[str, list[Any]] = {}
    for a in artifacts:
        phase = getattr(a, "phase", "?")
        artifacts_by_phase.setdefault(phase, []).append(a)

    gates_by_phase: dict[str, list[Any]] = {}
    for g in gates:
        phase = getattr(g, "phase", "?")
        gates_by_phase.setdefault(phase, []).append(g)

    console.print()
    for ledger in ledgers:
        phase = getattr(ledger, "phase", "?")
        used = getattr(ledger, "used_tokens", 0)
        budget = getattr(ledger, "budget_tokens", 0)
        phase_artifacts = artifacts_by_phase.get(phase, [])
        phase_gates = gates_by_phase.get(phase, [])
        failed_gates = [
            g for g in phase_gates if getattr(g, "status", None) and g.status.value == "failed"
        ]
        warn_gates = [
            g for g in phase_gates if getattr(g, "status", None) and g.status.value == "warning"
        ]

        phase_status = (
            "✓" if not failed_gates and not warn_gates else ("⚠" if not failed_gates else "✗")
        )
        parts = [f"  {phase_status} {phase.upper():<12}  {used}/{budget} tokens"]
        if phase_artifacts:
            kinds = ", ".join(getattr(a, "kind", "artifact") for a in phase_artifacts[:3])
            # Parentheses, not brackets — brackets are rich markup and would be
            # swallowed when routed through the brand console.
            parts.append(f"  ({kinds})")
        if failed_gates:
            parts.append(f"  FAILED: {', '.join(g.id for g in failed_gates)}")
        elif warn_gates:
            parts.append(f"  warn: {', '.join(g.id for g in warn_gates[:2])}")
        console.print("".join(parts))

    # LLM-absent warnings surfaced directly to user
    for w in warnings:
        if (
            "LLM" in w
            or "provider" in w
            or "delegate" in w
            or "executor" in w
            or "planned" in w.lower()
        ):
            console.warning(w)

    # Be honest about whether the loop actually wrote source. In-process apply
    # only runs when an executor produced concrete edits; otherwise the loop plans
    # and the host agent performs the edits. Don't let "Loop complete" read as
    # "code written" when it wasn't.
    apply_note = _apply_outcome(artifacts)
    if apply_note is not None:
        console.print(f"\n  {apply_note}")

    console.print(
        f"\n  Status: {status_str}  |  {len(artifacts)} artifact(s)  |  {len(gates)} gate(s)"
    )


def _apply_outcome(artifacts: list[Any]) -> str | None:
    """Report whether the apply phase wrote real source, read from its manifest."""
    import json

    for artifact in artifacts:
        path = str(getattr(artifact, "path", ""))
        if not path.endswith("apply-manifest.json"):
            continue
        try:
            manifest = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return None
        changes = manifest.get("changes", [])
        if manifest.get("status") == "applied" and changes:
            return f"✓ Apply wrote {len(changes)} file(s)."
        return "note: Apply was planned-only — no source written (the host agent performs edits)."
    return None


def _ask_continue(phase: str) -> bool:
    """Prompt user for continuation with a Yes/No selector. Returns True to continue."""
    # Checkpoints are a safety gate: never auto-continue on a non-interactive run.
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        from opencontext_core import prompts

        return prompts.confirm(f"Continue past {phase}?", default=True)
    except (EOFError, KeyboardInterrupt):
        return False
