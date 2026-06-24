"""``opencontext learn`` — inspect the learning system state and patterns.

Subcommands:
  status       Report the current learning system state (pattern count, budget count,
               last run statistics).
  patterns     List the patterns known to ``PatternLearner``.

This command is read-only: it never modifies patterns, budgets, or any
configuration.  Use ``opencontext harness run`` with ``learning.in_loop: true``
to trigger the learning cycle.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def add_learn_parser(subparsers: Any) -> None:
    """Register the ``learn`` command group."""
    learn_parser = subparsers.add_parser(
        "learn",
        help="Inspect learning system state and patterns.",
        description=(
            "Show the current state of the OpenContext learning system: "
            "pattern counts, budget profiles, and last-run statistics."
        ),
    )
    learn_sub = learn_parser.add_subparsers(dest="learn_command", required=True)

    # status
    status_parser = learn_sub.add_parser(
        "status",
        help="Show learning system status and statistics.",
    )
    status_parser.add_argument(
        "--root",
        default=".",
        help="Project root (default: current directory).",
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON.",
    )

    # patterns
    patterns_parser = learn_sub.add_parser(
        "patterns",
        help="List patterns known to PatternLearner.",
    )
    patterns_parser.add_argument(
        "--root",
        default=".",
        help="Project root (default: current directory).",
    )
    patterns_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON.",
    )


def handle_learn(args: argparse.Namespace) -> None:
    """Dispatch learn subcommands."""
    cmd = getattr(args, "learn_command", None)
    if cmd == "status":
        _handle_status(args)
    elif cmd == "patterns":
        _handle_patterns(args)
    else:
        print("learn: unknown subcommand. Use --help for usage.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_orchestrator(args: argparse.Namespace) -> Any:
    """Construct a LearningOrchestrator for the given project root."""
    from opencontext_core.learning.learning_orchestrator import LearningOrchestrator

    root = Path(getattr(args, "root", ".")).resolve()
    return LearningOrchestrator(
        storage_path=root / ".storage" / "opencontext" / "learning",
        kg_db_path=root / ".storage" / "opencontext" / "context_graph.db",
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_status(args: argparse.Namespace) -> None:
    import json as _json

    try:
        orch = _build_orchestrator(args)
        stats = orch.get_statistics()
    except Exception as exc:
        print(f"learn status: could not load learning system: {exc}")
        raise SystemExit(1) from exc

    as_json = getattr(args, "json", False)
    if as_json:
        print(_json.dumps(stats, indent=2, default=str))
        return

    patterns = stats.get("patterns", {})
    budgets = stats.get("budgets", {})
    feedback = stats.get("feedback", {})

    print("Learning system status")
    print("=" * 40)
    print(f"  Patterns known : {len(patterns)}")
    print(f"  Budget profiles: {len(budgets)}")
    total_ops = feedback.get("total_operations", feedback.get("total", "?"))
    print(f"  Total ops seen : {total_ops}")
    if patterns:
        avg_success = sum(
            v.get("success_rate", 0.0) for v in patterns.values()
        ) / len(patterns)
        print(f"  Avg success    : {avg_success:.0%}")


def _handle_patterns(args: argparse.Namespace) -> None:
    import json as _json

    try:
        orch = _build_orchestrator(args)
        all_patterns = orch.patterns.get_all_patterns()
    except Exception as exc:
        print(f"learn patterns: could not load patterns: {exc}")
        raise SystemExit(1) from exc

    as_json = getattr(args, "json", False)
    if as_json:
        serializable = {
            k: {
                "task_type": v.task_type,
                "success_rate": v.success_rate,
                "occurrence_count": v.occurrence_count,
                "avg_tokens_used": v.avg_tokens_used,
                "relevant_files": v.relevant_files[:5],
                "relevant_symbols": v.relevant_symbols[:5],
            }
            for k, v in all_patterns.items()
        }
        print(_json.dumps(serializable, indent=2))
        return

    if not all_patterns:
        print("No patterns known to PatternLearner.")
        return

    col_type = 30
    col_rate = 10
    col_count = 8
    header = f"{'TASK TYPE':<{col_type}}  {'SUCCESS':<{col_rate}}  {'COUNT':<{col_count}}"
    print(header)
    print("-" * len(header))
    for task_type, pattern in sorted(all_patterns.items()):
        print(
            f"{task_type:<{col_type}}  "
            f"{pattern.success_rate:.0%}{'':>{col_rate - 4}}  "
            f"{pattern.occurrence_count:<{col_count}}"
        )
