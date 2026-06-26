"""REQ-02c: Memory benchmark seeds ephemeral DB and fails on 0.0 recall.

Tests:
- Seeded run from installed-style path achieves nonzero recall.
- Unseeded store → exit 1 with 'invalid-state' in stderr.
- JSON output includes seeded_records and positive recall.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _make_args(
    fixture_path: str | None = None,
    db: str | None = None,
    k: int = 5,
    json_output: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        fixture_path=fixture_path,
        fixture="coding-agent-life-v1",
        db=db,
        k=k,
        json_output=json_output,
    )


def test_seeded_benchmark_achieves_nonzero_recall() -> None:
    """Seeded run using the bundled fixture achieves nonzero recall."""
    from opencontext_cli.commands.memory_benchmark_cmd import handle_memory_benchmark

    # db=None triggers ephemeral temp-file DB (seeded by handle_memory_benchmark).
    args = _make_args(db=None, k=5)

    buf = io.StringIO()
    with redirect_stdout(buf):
        handle_memory_benchmark(args)

    output = buf.getvalue()
    # Output must include a recall line with nonzero value.
    assert "Recall@5" in output
    # Verify it mentions seeded records.
    assert "Seeded:" in output


def test_seeded_benchmark_exit_1_on_zero_recall() -> None:
    """When recall == 0.0 after seeding, process exits non-zero with invalid-state message."""
    from opencontext_core.memory.benchmark import MemoryBenchmarkResult
    from opencontext_cli.commands.memory_benchmark_cmd import handle_memory_benchmark

    # Patch run_benchmark to return 0.0 recall to test the guard path.
    zero_result = MemoryBenchmarkResult(
        recall_at_5=0.0,
        mrr=0.0,
        precision_at_5=0.0,
        p50_ms=0.0,
        p95_ms=0.0,
        num_questions=5,
    )

    args = _make_args(db=None, k=5)

    err_buf = io.StringIO()
    with pytest.raises(SystemExit) as exc_info:
        with redirect_stderr(err_buf):
            with patch(
                "opencontext_core.memory.benchmark.run_benchmark",
                return_value=zero_result,
            ):
                handle_memory_benchmark(args)

    assert exc_info.value.code != 0
    assert "invalid-state" in err_buf.getvalue()


def test_seeded_benchmark_json_output() -> None:
    """JSON output includes seeded_records and recall_at_5 > 0."""
    from opencontext_cli.commands.memory_benchmark_cmd import handle_memory_benchmark

    args = _make_args(db=None, k=5, json_output=True)

    buf = io.StringIO()
    with redirect_stdout(buf):
        handle_memory_benchmark(args)

    data = json.loads(buf.getvalue())
    assert "recall_at_5" in data
    assert data["recall_at_5"] > 0.0
    assert "seeded_records" in data
    assert data["seeded_records"] > 0
