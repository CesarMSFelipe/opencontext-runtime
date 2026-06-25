"""Memory benchmark CLI command — ``opencontext memory benchmark``.

Runs the memory recall benchmark against a named fixture and prints results.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def add_memory_benchmark_parser(memory_sub: Any) -> None:
    """Register ``benchmark`` subcommand under the ``memory`` subparser group."""
    parser = memory_sub.add_parser(
        "benchmark",
        help="Benchmark memory recall (R@5, MRR, latency).",
        description=(
            "Run a reproducible memory recall benchmark against a named fixture.\n\n"
            "  opencontext memory benchmark --fixture coding-agent-life-v1 --json\n"
        ),
    )
    parser.add_argument(
        "--fixture",
        default="coding-agent-life-v1",
        help="Fixture name (without .json extension, default: coding-agent-life-v1).",
    )
    parser.add_argument(
        "--fixture-path",
        default=None,
        help="Explicit path to fixture JSON (overrides --fixture).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON.",
    )
    parser.add_argument(
        "--db",
        default=".opencontext/memory.db",
        help="Path to memory SQLite database (default: .opencontext/memory.db).",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Recall@k parameter (default: 5).",
    )


def handle_memory_benchmark(args: Any) -> None:
    """Handle ``opencontext memory benchmark`` invocation."""
    from opencontext_core.memory.backends import SQLiteMemoryBackend
    from opencontext_core.memory.benchmark import run_benchmark

    # Resolve fixture path.
    if getattr(args, "fixture_path", None):
        fixture_path = Path(args.fixture_path)
    else:
        fixture_name = getattr(args, "fixture", "coding-agent-life-v1")
        # Search bundled fixtures dir relative to this file's package.
        candidates = [
            Path(__file__).parent.parent.parent.parent.parent
            / "tests"
            / "fixtures"
            / "memory"
            / f"{fixture_name}.json",
            Path("tests") / "fixtures" / "memory" / f"{fixture_name}.json",
            Path(fixture_name + ".json"),
        ]
        fixture_path = None
        for candidate in candidates:
            if candidate.exists():
                fixture_path = candidate
                break
        if fixture_path is None:
            print(
                f"Error: fixture {fixture_name!r} not found. Searched:\n"
                + "\n".join(f"  {c}" for c in candidates)
                + "\nTip: supply an explicit path with --fixture-path <path>.",
                file=sys.stderr,
            )
            raise SystemExit(1)

    db_path = getattr(args, "db", ".opencontext/memory.db")
    k = getattr(args, "k", 5)
    json_output = getattr(args, "json_output", False)

    backend = SQLiteMemoryBackend(db_path)
    result = run_benchmark(fixture_path, backend, k=k)

    if json_output:
        output = {
            "recall_at_5": result.recall_at_5,
            "mrr": result.mrr,
            "precision_at_5": result.precision_at_5,
            "p50_ms": result.p50_ms,
            "p95_ms": result.p95_ms,
            "num_questions": result.num_questions,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Memory benchmark results (fixture: {fixture_path.name})")
        print(f"  Questions:    {result.num_questions}")
        print(f"  Recall@{k}:    {result.recall_at_5:.3f}")
        print(f"  MRR:          {result.mrr:.3f}")
        print(f"  Precision@{k}: {result.precision_at_5:.3f}")
        print(f"  Latency p50:  {result.p50_ms:.1f} ms")
        print(f"  Latency p95:  {result.p95_ms:.1f} ms")
        if result.recall_at_5 == 0.0:
            print(
                "\nNote: Recall@k is 0.0 — the memory store appears empty or has no relevant "
                "records. Populate the store with 'opencontext memory harvest' (or run an "
                "agentic loop) to see meaningful recall scores."
            )
