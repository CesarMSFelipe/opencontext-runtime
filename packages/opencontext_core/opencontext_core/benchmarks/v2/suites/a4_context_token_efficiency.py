"""A4 — context token efficiency: compression engine wired (CH-2 gate).

Builds a seeded tmp project with a substantial knowledge_graph.json, runs
``ContextSubstrateBuilder.build_for_phase`` in-process, and asserts that:

1. ``compression_enabled`` is ``True`` — the CH-2 compression wiring fired.
2. ``selected_tokens > 0`` — the KG content was measured (token count present).
3. ``reduction_ratio >= THRESHOLD`` — no negative savings (engine is safe).

Threshold notes:
  SMART_CRUSHER processes JSON-structured KG content losslessly (tabular-only
  compression applies only when the engine detects repeated tabular rows).  A
  threshold of 0.0 is therefore honest for this content shape: it proves CH-2
  is wired and the engine ran without exception, without fabricating a reduction
  that the engine does not produce on this format.  The metric is recorded in
  ``report.compression_savings / report.baseline_tokens`` for observability.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "A4"

# Threshold for token reduction ratio (compression_savings / baseline_tokens).
# SMART_CRUSHER applied to JSON KG content is lossless (0.0 savings expected).
# Threshold=0.0 confirms the engine ran without negative savings (no bloat).
_REDUCTION_THRESHOLD = 0.0


def _build_kg_payload(node_count: int = 80) -> dict:
    """Build a representative KG with nodes + call edges (non-trivial JSON)."""
    nodes = [
        {
            "id": f"symbol_{i}",
            "kind": "function",
            "file": f"src/module_{i // 10}.py",
            "content": (
                f"def symbol_{i}(arg1, arg2):  # implementation detail for node {i}\n"
                f"    return arg1 + arg2 + {i}"
            ),
        }
        for i in range(node_count)
    ]
    edges = [
        {"from": f"symbol_{i}", "to": f"symbol_{(i + 1) % node_count}", "type": "calls"}
        for i in range(0, node_count, 2)
    ]
    return {"nodes": nodes, "edges": edges}


def run() -> BenchmarkResult:
    """Seed a tmp project and verify the compression engine fires in-process."""
    # Isolate storage so build_for_phase writes substrate_report.json to tmp.
    saved_mode = os.environ.get("OPENCONTEXT_STORAGE_MODE")
    os.environ["OPENCONTEXT_STORAGE_MODE"] = "local"
    try:
        return _run_inner()
    finally:
        if saved_mode is None:
            os.environ.pop("OPENCONTEXT_STORAGE_MODE", None)
        else:
            os.environ["OPENCONTEXT_STORAGE_MODE"] = saved_mode


def _run_inner() -> BenchmarkResult:
    try:
        from opencontext_core.agentic.context_substrate import ContextSubstrateBuilder
    except ImportError as exc:
        return BenchmarkResult(
            name=SUITE_ID,
            success=False,
            methodology_version=current_methodology_version(),
            detail=f"ContextSubstrateBuilder import failed: {exc}",
        )

    with tempfile.TemporaryDirectory(prefix="oc_bench_a4_") as tmpdir_s:
        tmpdir = Path(tmpdir_s)
        oc_dir = tmpdir / ".opencontext"
        oc_dir.mkdir()
        kg = _build_kg_payload(node_count=80)
        (oc_dir / "knowledge_graph.json").write_text(
            json.dumps(kg, indent=2), encoding="utf-8"
        )

        try:
            builder = ContextSubstrateBuilder(root=tmpdir)
            report = builder.build_for_phase(
                task="context-token-efficiency-benchmark",
                phase="explore",
                budget=4000,
            )
        except Exception as exc:
            return BenchmarkResult(
                name=SUITE_ID,
                success=False,
                methodology_version=current_methodology_version(),
                detail=f"build_for_phase raised: {exc}",
            )

        # Gate 1: compression engine must have fired.
        if not report.compression_enabled:
            warnings_text = "; ".join(report.warnings) if report.warnings else "none"
            return BenchmarkResult(
                name=SUITE_ID,
                success=False,
                methodology_version=current_methodology_version(),
                detail=(
                    f"compression_enabled=False — CH-2 wiring not active; "
                    f"warnings: {warnings_text}"
                ),
            )

        # Gate 2: token counts must be present (KG was measured).
        if report.selected_tokens <= 0:
            return BenchmarkResult(
                name=SUITE_ID,
                success=False,
                methodology_version=current_methodology_version(),
                detail=(
                    f"selected_tokens={report.selected_tokens} — "
                    "KG token count missing; index may not have been read"
                ),
            )

        # Gate 3: reduction ratio must be >= threshold (no negative savings).
        baseline = report.baseline_tokens or report.selected_tokens
        ratio = report.compression_savings / baseline if baseline > 0 else 0.0
        if ratio < _REDUCTION_THRESHOLD:
            return BenchmarkResult(
                name=SUITE_ID,
                success=False,
                methodology_version=current_methodology_version(),
                detail=(
                    f"reduction_ratio={ratio:.4f} < threshold={_REDUCTION_THRESHOLD}; "
                    f"compression_savings={report.compression_savings}, "
                    f"baseline_tokens={baseline}"
                ),
            )

        return BenchmarkResult(
            name=SUITE_ID,
            success=True,
            methodology_version=current_methodology_version(),
            detail="",
            metrics={
                "compression_enabled": report.compression_enabled,
                "baseline_tokens": baseline,
                "selected_tokens": report.selected_tokens,
                "compressed_tokens": report.compressed_tokens,
                "compression_savings": report.compression_savings,
                "reduction_ratio": ratio,
            },
        )
