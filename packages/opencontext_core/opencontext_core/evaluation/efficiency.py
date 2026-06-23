"""The honest efficiency benchmark: CON (with OpenContext) vs realistic SIN.

This is a thin measurement harness over two runners that emit the SAME cost triple,
joined by the existing quality-parity gate:

* **CON** — a single ``runtime.prepare_context`` call (KG + compression + memory).
  Cost = pack tokens, 1 tool call, wall-clock. Reuses
  :meth:`ContextBenchEvaluator.evaluate_efficiency_case`.
* **SIN** — a realistic OpenContext-free ``grep`` + full-``Read`` loop over the
  working tree (:mod:`opencontext_core.evaluation.naive_agent`).

The report carries measured numbers only — NO "X% reduction"/badge/claim string. CI
gates on quality-parity (all CON packs sufficient), never on a reduction threshold.

Index hygiene (D-INDEX): the suite refreshes the index ONCE on the first case, then
pins it (``refresh_index=False``) for the rest, so all cases share one snapshot and
the run is reproducible. ``--no-refresh`` (``refresh_index=False`` here) documents the
pinned-index precondition for CI speed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from opencontext_core.evaluation.evaluator import ContextBenchEvaluator
from opencontext_core.evaluation.models import (
    ContextBenchCase,
    EfficiencyCaseResult,
    EfficiencyReport,
)
from opencontext_core.runtime import OpenContextRuntime

# Reuse the same on-disk location as the legacy benchmark persistence.
BENCHMARK_DIR = ".opencontext/benchmarks"


class EfficiencyBenchmark:
    """Runs the CON-vs-SIN efficiency benchmark over context-bench cases."""

    def __init__(
        self,
        runtime: OpenContextRuntime,
        *,
        root: str | Path = ".",
        max_tokens: int = 6000,
    ) -> None:
        self.runtime = runtime
        self.root = Path(root)
        self.max_tokens = max_tokens
        self._evaluator = ContextBenchEvaluator(
            runtime,
            root=self.root,
            max_tokens=max_tokens,
        )

    def evaluate_case(
        self,
        case: ContextBenchCase,
        *,
        refresh_index: bool = False,
    ) -> EfficiencyCaseResult:
        """Measure one case (CON vs SIN) under the mandatory quality-parity gate."""
        return self._evaluator.evaluate_efficiency_case(case, refresh_index=refresh_index)

    def evaluate_suite(
        self,
        cases: list[ContextBenchCase],
        *,
        refresh_index: bool = True,
    ) -> EfficiencyReport:
        """Measure every case; refresh the index once on the first case then pin it.

        When ``refresh_index`` is False the run uses the existing pinned index for all
        cases (CI fast path); the caller asserts the precondition.
        """
        results: list[EfficiencyCaseResult] = []
        for position, case in enumerate(cases):
            do_refresh = refresh_index and position == 0
            results.append(self.evaluate_case(case, refresh_index=do_refresh))
        return EfficiencyReport(cases=results)


# ── Report formatting (measured numbers only — no claim) ─────────────────────


def format_efficiency_report(report: EfficiencyReport) -> str:
    """Human-readable per-case CON vs SIN cost + deltas + parity, plus aggregates.

    Deliberately emits raw token/tool-call/latency numbers and their deltas — no
    "X% reduction"/badge/marketing string anywhere (ED8/EB-6).
    """
    lines = [
        "OpenContext efficiency benchmark (context WITH OpenContext vs grep+Read control)",
        "",
        f"{'case':28} {'parity':>8}  {'CON tok':>8} {'SIN tok':>8} {'Δtok':>8}  "
        f"{'CON calls':>9} {'SIN calls':>9}  {'CON ms':>7} {'SIN ms':>7}",
        "-" * 110,
    ]
    for case in report.cases:
        parity = "ok" if case.con_sufficient else "INSUFF"
        lines.append(
            f"{case.case_id[:28]:28} {parity:>8}  "
            f"{case.con.tokens:>8} {case.sin.tokens:>8} {case.token_delta:>8}  "
            f"{case.con.tool_calls:>9} {case.sin.tool_calls:>9}  "
            f"{case.con.latency_ms:>7.0f} {case.sin.latency_ms:>7.0f}"
        )
        if case.ceiling_tokens is not None:
            lines.append(
                f"{'':28} {'':>8}  (whole-repo ceiling: {case.ceiling_tokens} tok — secondary)"
            )
        if not case.con_sufficient:
            for reason in case.reasons:
                lines.append(f"{'':30}- {reason}")
    lines += [
        "-" * 110,
        f"  cases                 : {len(report.cases)} "
        f"({report.insufficient_cases} parity-insufficient)",
        f"  median token delta    : {report.median_token_delta} (SIN - CON)",
        f"  median tool-call delta: {report.median_tool_call_delta} (SIN - CON)",
        f"  CON latency p50 / p95 : {report.con_latency_p(50):.0f} / "
        f"{report.con_latency_p(95):.0f} ms",
        f"  SIN latency p50 / p95 : {report.sin_latency_p(50):.0f} / "
        f"{report.sin_latency_p(95):.0f} ms",
    ]
    return "\n".join(lines)


def format_efficiency_report_json(report: EfficiencyReport) -> str:
    """Serialize the report as JSON (measured numbers only, no claim field)."""
    payload = {
        "cases": [_case_to_dict(c) for c in report.cases],
        "aggregates": {
            "total_cases": len(report.cases),
            "insufficient_cases": report.insufficient_cases,
            "all_sufficient": report.all_sufficient,
            "median_token_delta": report.median_token_delta,
            "median_tool_call_delta": report.median_tool_call_delta,
            "con_latency_p50_ms": report.con_latency_p(50),
            "con_latency_p95_ms": report.con_latency_p(95),
            "sin_latency_p50_ms": report.sin_latency_p(50),
            "sin_latency_p95_ms": report.sin_latency_p(95),
        },
    }
    return json.dumps(payload, indent=2)


def _case_to_dict(case: EfficiencyCaseResult) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "difficulty": case.difficulty,
        "con": case.con.model_dump(mode="json"),
        "sin": case.sin.model_dump(mode="json"),
        "ceiling_tokens": case.ceiling_tokens,
        "con_sufficient": case.con_sufficient,
        "source_coverage": case.source_coverage,
        "forbidden_hits": case.forbidden_hits,
        "token_delta": case.token_delta,
        "tool_call_delta": case.tool_call_delta,
        "reasons": case.reasons,
    }


# ── Persistence (reuses BENCHMARK_DIR; round-trips EfficiencyReport) ──────────


def save_efficiency_result(
    report: EfficiencyReport,
    directory: str | Path = BENCHMARK_DIR,
) -> Path:
    """Save the report as a timestamped JSON file; returns the written path."""
    dest = Path(directory)
    dest.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = dest / f"{timestamp}-efficiency.json"
    path.write_text(
        json.dumps({"cases": [_case_to_dict(c) for c in report.cases]}, indent=2),
        encoding="utf-8",
    )
    return path


def load_last_efficiency_result(
    directory: str | Path = BENCHMARK_DIR,
) -> EfficiencyReport | None:
    """Load the most recent efficiency report from a directory, or None."""
    dest = Path(directory)
    if not dest.exists():
        return None
    files = sorted(dest.glob("*-efficiency.json"), reverse=True)
    if not files:
        return None
    data = json.loads(files[0].read_text(encoding="utf-8"))
    cases = [EfficiencyCaseResult.model_validate(_case_from_dict(c)) for c in data.get("cases", [])]
    return EfficiencyReport(cases=cases)


def _case_from_dict(data: dict[str, object]) -> dict[str, object]:
    """Drop the derived (read-only property) keys before model validation."""
    return {k: v for k, v in data.items() if k not in ("token_delta", "tool_call_delta")}
