"""Memory benchmark CLI command — ``opencontext memory benchmark``.

Runs the memory recall benchmark against a named fixture and prints results.
The fixture corpus is resolved via ``importlib.resources`` so this works from
a pip-installed location where no ``tests/`` directory exists.

Before measuring, an ephemeral SQLite DB is seeded with the fixture corpus.
If the store remains unseeded (recall == 0.0), the command exits non-zero with
an explicit ``invalid-state`` message rather than reporting a green 0.0.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
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
        default=None,
        help=(
            "Path to memory SQLite database. "
            "When omitted, an ephemeral temp-file DB is seeded and used (default)."
        ),
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Recall@k parameter (default: 5).",
    )


def _resolve_fixture(args: Any) -> Path:
    """Return the path to the fixture JSON file.

    Resolution order:
    1. Explicit ``--fixture-path`` argument.
    2. ``importlib.resources`` from the installed package (works pip-installed).
    3. Fallback: relative paths searched from cwd / this file's parents.
    """
    if getattr(args, "fixture_path", None):
        path = Path(args.fixture_path)
        if path.exists():
            return path
        print(
            f"Error: fixture path {args.fixture_path!r} does not exist.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    fixture_name = getattr(args, "fixture", "coding-agent-life-v1")

    # Primary: importlib.resources — works from pip-installed locations.
    try:
        import importlib.resources as _ilr

        fixture_ref = _ilr.files("opencontext_cli").joinpath(
            f"fixtures/memory/{fixture_name}.json"
        )
        if fixture_ref.is_file():
            # Materialise the resource as a real Path object via as_file().
            # For an editable install this is already a real path; for a zip
            # package it creates a temporary file.
            with _ilr.as_file(fixture_ref) as real_path:
                # Copy content to a temp file so the context manager can exit safely.
                import shutil

                tmp = Path(tempfile.mktemp(suffix=".json"))
                shutil.copy2(str(real_path), str(tmp))
                return tmp
    except Exception:
        pass

    # Fallback: search well-known relative paths (dev environment only).
    fallback_candidates = [
        Path(__file__).parent.parent.parent.parent.parent
        / "tests"
        / "fixtures"
        / "memory"
        / f"{fixture_name}.json",
        Path("tests") / "fixtures" / "memory" / f"{fixture_name}.json",
        Path(fixture_name + ".json"),
    ]
    for candidate in fallback_candidates:
        if candidate.exists():
            return candidate

    print(
        f"Error: fixture {fixture_name!r} not found via importlib.resources or fallback paths.\n"
        "Searched:\n"
        + "\n".join(f"  {c}" for c in fallback_candidates)
        + "\nTip: supply an explicit path with --fixture-path <path>.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _seed_backend(fixture_path: Path, backend: Any) -> int:
    """Seed *backend* with memory records derived from the fixture corpus.

    For each (query, relevant_id) pair in the fixture, creates a MemoryRecord
    whose key is the relevant_id and whose content includes the query text so
    that FTS5/BM25 search can retrieve it.

    Returns the number of records written.
    """
    from datetime import UTC, datetime

    from opencontext_core.models.agent_memory import (
        DecayPolicy,
        MemoryLayer,
        MemoryRecord,
    )

    raw: list[dict[str, Any]] = json.loads(fixture_path.read_text(encoding="utf-8"))
    now = datetime.now(tz=UTC)
    count = 0
    for item in raw:
        query: str = item.get("query", "")
        relevant: list[str] = item.get("relevant", [])
        metadata: dict[str, Any] = item.get("metadata", {})
        domain = metadata.get("domain", "general")
        phase = metadata.get("phase", "apply")

        for rel_id in relevant:
            # Content combines the query text and relevant ID so FTS5 can match
            # on either the domain term or the query keywords.
            content = (
                f"{query}. "
                f"Key: {rel_id}. "
                f"Domain: {domain}. Phase: {phase}."
            )
            record = MemoryRecord(
                id=f"bench:{rel_id}",
                layer=MemoryLayer.SEMANTIC,
                key=rel_id,
                content=content,
                decay_policy=DecayPolicy(enabled=False),
                created_at=now,
                updated_at=now,
            )
            backend.store(record)
            count += 1

    return count


def handle_memory_benchmark(args: Any) -> None:
    """Handle ``opencontext memory benchmark`` invocation."""
    from opencontext_core.memory.backends import SQLiteMemoryBackend
    from opencontext_core.memory.benchmark import run_benchmark

    fixture_path = _resolve_fixture(args)

    db_path = getattr(args, "db", None)
    k = getattr(args, "k", 5)
    json_output = getattr(args, "json_output", False)

    # Use an ephemeral temp-file SQLite DB when no explicit path is given.
    # NOTE: Cannot use ":memory:" because SQLiteMemoryBackend opens a new connection
    # per operation, so in-memory DBs lose their schema/data between calls.
    _tmp_db_path: str | None = None
    if not db_path:
        _fd, _tmp_db_path = tempfile.mkstemp(suffix=".benchmark.db", prefix="oc_mem_bench_")
        os.close(_fd)
        db_path = _tmp_db_path

    try:
        backend = SQLiteMemoryBackend(db_path)

        # NOTE: REQ-02c — seed the ephemeral DB before measuring.
        seeded_count = _seed_backend(fixture_path, backend)

        result = run_benchmark(fixture_path, backend, k=k)
    finally:
        # Clean up the ephemeral temp DB file.
        if _tmp_db_path and Path(_tmp_db_path).exists():
            try:
                Path(_tmp_db_path).unlink()
            except OSError:
                pass

    # NOTE: REQ-02c — invalid-state guard: fail loudly if store returned 0.0 recall.
    if result.recall_at_5 == 0.0:
        print(
            f"invalid-state: seeded store returned 0.0 recall after seeding {seeded_count} record(s). "
            "The memory backend search may not be functioning correctly.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if json_output:
        output = {
            "recall_at_5": result.recall_at_5,
            "mrr": result.mrr,
            "precision_at_5": result.precision_at_5,
            "p50_ms": result.p50_ms,
            "p95_ms": result.p95_ms,
            "num_questions": result.num_questions,
            "seeded_records": seeded_count,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Memory benchmark results (fixture: {fixture_path.name})")
        print(f"  Questions:    {result.num_questions}")
        print(f"  Seeded:       {seeded_count} record(s)")
        print(f"  Recall@{k}:    {result.recall_at_5:.3f}")
        print(f"  MRR:          {result.mrr:.3f}")
        print(f"  Precision@{k}: {result.precision_at_5:.3f}")
        print(f"  Latency p50:  {result.p50_ms:.1f} ms")
        print(f"  Latency p95:  {result.p95_ms:.1f} ms")
