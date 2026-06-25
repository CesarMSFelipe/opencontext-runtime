"""Memory benchmark — R@k, MRR, precision@k, and p50 latency harness.

Uses the existing ``SQLiteMemoryBackend.search()`` (FTS5+bm25) — no separate
BM25 implementation. Fixture format: list of objects with "query" and
"relevant" (list of doc IDs / key substrings that count as a hit).
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def recall_at_k(results: list[str], relevant: list[str], k: int) -> float:
    """Recall@k: fraction of relevant items found in the top-k results.

    Pure function with no I/O side effects.
    """
    if not relevant:
        return 0.0
    top_k = results[:k]
    hits = sum(1 for r in top_k if r in relevant)
    return hits / len(relevant)


def precision_at_k(results: list[str], relevant: list[str], k: int) -> float:
    """Precision@k: fraction of top-k results that are relevant.

    Pure function with no I/O side effects.
    """
    if k == 0:
        return 0.0
    top_k = results[:k]
    hits = sum(1 for r in top_k if r in relevant)
    return hits / k


def reciprocal_rank(results: list[str], relevant: list[str]) -> float:
    """Reciprocal rank: 1/(position of first relevant item, 1-based).

    Returns 0.0 when no relevant item appears in results.
    Pure function with no I/O side effects.
    """
    for idx, result in enumerate(results):
        if result in relevant:
            return 1.0 / (idx + 1)
    return 0.0


@dataclass
class MemoryBenchmarkQuestion:
    """A single benchmark question with expected relevant doc IDs."""

    query: str
    relevant: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryBenchmarkResult:
    """Aggregated result of running the memory benchmark."""

    recall_at_5: float
    mrr: float
    precision_at_5: float
    p50_ms: float
    p95_ms: float
    num_questions: int
    details: list[dict[str, Any]] = field(default_factory=list)


def run_benchmark(
    fixture_path: Path | str,
    backend: Any,
    k: int = 5,
) -> MemoryBenchmarkResult:
    """Run the benchmark fixture against *backend*.

    ``backend`` must support ``.search(query, limit=k)`` returning objects
    with ``.key`` or ``.id`` attributes (``SQLiteMemoryBackend`` contract).

    Fixture JSON: list of ``{query: str, relevant: [str, ...], ...}`` objects.
    Matching: a result's ``.key`` is a hit when any ``relevant`` entry is a
    substring of ``.key``, or matches ``.id`` exactly.
    """
    path = Path(fixture_path)
    raw: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    questions = [
        MemoryBenchmarkQuestion(
            query=item["query"],
            relevant=item["relevant"],
            metadata=item.get("metadata", {}),
        )
        for item in raw
    ]

    recall_scores: list[float] = []
    rr_scores: list[float] = []
    precision_scores: list[float] = []
    latencies_ms: list[float] = []
    details: list[dict[str, Any]] = []

    for q in questions:
        t0 = time.perf_counter()
        records = backend.search(q.query, limit=k)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

        # Build result IDs for metric computation.
        result_ids: list[str] = []
        for rec in records:
            key = str(getattr(rec, "key", None) or getattr(rec, "id", ""))
            result_ids.append(key)

        # Hit: any relevant entry appears as substring of result key or exact id.
        def _is_hit(result_key: str, rel_list: list[str]) -> bool:
            return any(rel in result_key for rel in rel_list)

        hit_flags = [_is_hit(rid, q.relevant) for rid in result_ids]
        matched_ids = [rid for rid, hit in zip(result_ids, hit_flags, strict=True) if hit]

        r5 = recall_at_k(matched_ids, q.relevant, k)
        p5 = precision_at_k(matched_ids, q.relevant, k)
        rr = reciprocal_rank(matched_ids, q.relevant)

        recall_scores.append(r5)
        precision_scores.append(p5)
        rr_scores.append(rr)

        details.append(
            {
                "query": q.query,
                "recall_at_k": r5,
                "precision_at_k": p5,
                "reciprocal_rank": rr,
                "latency_ms": elapsed_ms,
                "result_ids": result_ids,
            }
        )

    latencies_ms_sorted = sorted(latencies_ms)
    n = len(latencies_ms_sorted)
    p50_ms = statistics.median(latencies_ms_sorted) if n else 0.0
    p95_idx = max(0, int(n * 0.95) - 1)
    p95_ms = latencies_ms_sorted[p95_idx] if latencies_ms_sorted else 0.0

    return MemoryBenchmarkResult(
        recall_at_5=sum(recall_scores) / len(recall_scores) if recall_scores else 0.0,
        mrr=sum(rr_scores) / len(rr_scores) if rr_scores else 0.0,
        precision_at_5=sum(precision_scores) / len(precision_scores) if precision_scores else 0.0,
        p50_ms=p50_ms,
        p95_ms=p95_ms,
        num_questions=len(questions),
        details=details,
    )
