"""Interactive agentic loop — SDD workflow with user checkpoints."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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


def add_loop_commands(subparsers: argparse._SubParsersAction) -> None:
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


def handle_loop(args: argparse.Namespace, config=None) -> int:
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
        print("\nDry run — phases that would execute:")
        for p in phases:
            print(f"  - {p.upper()}")
        return 0

    manifest_path = root / ".storage" / "opencontext" / "project_manifest.json"
    if not manifest_path.exists():
        print("No index found. Run 'opencontext index .' first, then retry.")
        return 1

    try:
        from opencontext_core.backends.factory import BackendFactory

        compressor = BackendFactory.create_compression_backend(compress_mode)
    except Exception:
        compressor = None

    for round_num in range(1, max_rounds + 1):
        if max_rounds > 1:
            print(f"\n-- Round {round_num}/{max_rounds} --")

        success = _run_loop(task, workflow, root, config, compressor, autonomous)
        if success:
            break
        if round_num < max_rounds:
            print(f"\nRound {round_num} incomplete. Retrying...")
        else:
            print(f"\nLoop did not complete after {max_rounds} round(s).")
            return 1

    return 0


def _run_loop(
    task: str,
    workflow: str,
    root: Path,
    config,
    compressor,
    autonomous: bool,
) -> bool:
    """Execute one loop iteration. Returns True if all phases completed."""
    try:
        from opencontext_core.harness.runner import HarnessRunner
    except ImportError as e:
        print(f"Runtime not available: {e}", file=sys.stderr)
        return False

    runner = HarnessRunner(root=root)

    try:
        result = runner.run(workflow, task)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return False

    _print_run_summary(result)
    status = getattr(result, "status", None)
    passed = status is not None and getattr(status, "value", str(status)) in ("passed", "warning")
    if passed:
        print("\nLoop complete.")
    elif not passed:
        print("\nLoop did not complete — check warnings above.")
    return passed


def _print_header(task: str, flow: str, compress: str) -> None:
    width = 60
    print("-" * width)
    print(f"  OpenContext Loop  [{flow}]  compress:{compress}")
    print(f"  Task: {task[: width - 8]}")
    print("-" * width)


def _print_run_summary(result) -> None:
    """Print a human-readable run summary with per-phase breakdown."""
    if result is None:
        print("  no result")
        return

    ledgers = getattr(result, "ledgers", [])
    artifacts = getattr(result, "artifacts", [])
    warnings = getattr(result, "warnings", [])
    gates = getattr(result, "gates", [])
    status = getattr(result, "status", None)
    status_str = status.value if hasattr(status, "value") else str(status)

    # Per-phase summary
    artifacts_by_phase: dict[str, list] = {}
    for a in artifacts:
        phase = getattr(a, "phase", "?")
        artifacts_by_phase.setdefault(phase, []).append(a)

    gates_by_phase: dict[str, list] = {}
    for g in gates:
        phase = getattr(g, "phase", "?")
        gates_by_phase.setdefault(phase, []).append(g)

    print()
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
            parts.append(f"  [{kinds}]")
        if failed_gates:
            parts.append(f"  FAILED: {', '.join(g.id for g in failed_gates)}")
        elif warn_gates:
            parts.append(f"  warn: {', '.join(g.id for g in warn_gates[:2])}")
        print("".join(parts))

    # LLM-absent warnings surfaced directly to user
    for w in warnings:
        if (
            "LLM" in w
            or "provider" in w
            or "delegate" in w
            or "executor" in w
            or "planned" in w.lower()
        ):
            print(f"\n  ⚠  {w}")

    print(f"\n  Status: {status_str}  |  {len(artifacts)} artifact(s)  |  {len(gates)} gate(s)")


def _ask_continue(phase: str) -> bool:
    """Prompt user for continuation. Returns True to continue."""
    try:
        ans = input(f"  Continue past {phase}? [Y/n] ").strip().lower()
        return ans in ("", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False
