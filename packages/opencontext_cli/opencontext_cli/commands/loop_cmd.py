"""Interactive agentic loop — SDD workflow with user checkpoints."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

FLOWS = {
    "quick":     ["explore", "apply", "verify"],
    "standard":  ["explore", "spec", "design", "apply", "verify"],
    "full":      ["explore", "propose", "spec", "design", "tasks", "apply", "verify", "archive"],
    "autonomous": None,  # all phases, no user prompts
}

COMPRESSION_MODES = ["terse", "compact", "efficient", "none"]


def add_loop_commands(subparsers: argparse._SubParsersAction) -> None:
    loop = subparsers.add_parser(
        "loop",
        help="Interactive agentic workflow loop with user checkpoints.",
    )
    loop.add_argument("--task", "-t", required=True, help="Task description")
    loop.add_argument(
        "--flow", choices=list(FLOWS.keys()), default="full",
        help="Workflow track: quick/standard/full/autonomous",
    )
    loop.add_argument(
        "--compress", choices=COMPRESSION_MODES, default="efficient",
        help="Compression mode for agent output (default: efficient)",
    )
    loop.add_argument(
        "--root", default=".", help="Project root directory",
    )
    loop.add_argument(
        "--max-rounds", type=int, default=1,
        help="Max loop iterations (>1 = retry on failure)",
    )
    loop.add_argument(
        "--autonomous", action="store_true",
        help="Skip user prompts — gates decide (same as --flow autonomous)",
    )
    loop.add_argument(
        "--dry-run", action="store_true",
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

    phases = FLOWS.get(flow) or FLOWS["full"]

    # ponytail: hardcoded default storage path — matches runtime default
    manifest_path = root / ".storage" / "opencontext" / "project_manifest.json"
    if not manifest_path.exists():
        print("No index found. Run 'opencontext index .' first, then retry.")
        return 1

    _print_header(task, flow, compress_mode)

    if dry_run:
        print("\nDry run — phases that would execute:")
        for p in phases:
            print(f"  - {p.upper()}")
        return 0

    # Build compressor for output
    try:
        from opencontext_core.backends.factory import BackendFactory
        compressor = BackendFactory.create_compression_backend(compress_mode)
    except Exception:
        compressor = None

    for round_num in range(1, max_rounds + 1):
        if max_rounds > 1:
            print(f"\n-- Round {round_num}/{max_rounds} --")

        success = _run_loop(task, phases, root, config, compressor, autonomous)
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
    phases: list[str],
    root: Path,
    config,
    compressor,
    autonomous: bool,
) -> bool:
    """Execute one loop iteration. Returns True if all phases completed."""
    try:
        from opencontext_core.harness.models import HarnessRunState
        from opencontext_core.harness.runner import HarnessRunner
    except ImportError as e:
        print(f"Runtime not available: {e}", file=sys.stderr)
        return False

    state = HarnessRunState(task=task, root=root)
    runner = HarnessRunner(config=config)

    for phase in phases:
        print(f"\n{phase.upper()}", end="  ", flush=True)

        try:
            result = runner.run_phase(phase, state)
        except Exception as e:
            print(f"error: {e}")
            return False

        # Compress and display summary
        summary = _summarize_phase(result, compressor)
        print(summary)

        # User checkpoint (not in autonomous mode)
        if not autonomous and phase not in ("archive",):
            if not _ask_continue(phase):
                print("\nAborted by user.")
                return False

    print("\nLoop complete.")
    return True


def _print_header(task: str, flow: str, compress: str) -> None:
    width = 60
    print("-" * width)
    print(f"  OpenContext Loop  [{flow}]  compress:{compress}")
    print(f"  Task: {task[:width - 8]}")
    print("-" * width)


def _summarize_phase(result, compressor) -> str:
    """Produce a compressed one-line summary of a phase result."""
    if result is None:
        return "skipped"
    status = getattr(result, "status", "?")
    gates = getattr(result, "gates", [])
    passed = sum(1 for g in gates if getattr(g, "status", None) and g.status.value == "passed")
    total = len(gates)
    summary = f"status:{status.value if hasattr(status, 'value') else status}"
    if total:
        summary += f"  gates:{passed}/{total}"
    artifacts = getattr(result, "artifacts", [])
    if artifacts:
        summary += f"  artifacts:{len(artifacts)}"
    if compressor:
        try:
            summary = compressor.compress(summary, [])
        except Exception:
            pass
    return summary


def _ask_continue(phase: str) -> bool:
    """Prompt user for continuation. Returns True to continue."""
    try:
        ans = input(f"  Continue past {phase}? [Y/n] ").strip().lower()
        return ans in ("", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False
