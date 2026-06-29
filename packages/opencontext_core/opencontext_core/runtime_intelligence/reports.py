"""Text/JSON renderers for the Runtime Intelligence report family (book §5).

Plain, dependency-free renderers so the CLI (and Studio later, PR-014) can surface
the typed reports. JSON rendering defers to pydantic ``model_dump_json``; text
rendering produces compact, claim-free summaries.
"""

from __future__ import annotations

import json

from opencontext_core.models.intelligence import (
    BenchmarkResult,
    ConfidenceReport,
    CostReport,
    ProfilerReport,
    RuntimeHealthReport,
    SimulationReport,
    WorkflowComparison,
)


def to_json(report: object) -> str:
    """Serialize any report model to indented JSON."""
    if hasattr(report, "model_dump_json"):
        return str(report.model_dump_json(indent=2))
    return json.dumps(report, indent=2, default=str)


def render_cost_report(report: CostReport) -> str:
    lines = [
        f"Cost report — run {report.run_id} (workflow={report.estimate.workflow})",
        f"  estimated tokens : {report.estimate.estimated_input_tokens}"
        f" in / {report.estimate.estimated_output_tokens} out",
        f"  actual tokens    : {report.actual_input_tokens} in / {report.actual_output_tokens} out",
        f"  estimate error   : {report.estimate_error_pct:+.1f}%",
        f"  tool calls       : {report.actual_tool_calls}",
        f"  duration         : {report.actual_duration_s}s",
    ]
    if report.token_savings:
        ts = report.token_savings
        lines.append(
            f"  token savings    : {ts.get('saved', 0)} "
            f"(naive {ts.get('naive', 0)} - optimized {ts.get('optimized', 0)})"
        )
    if report.cost_by_component:
        lines.append("  cost by component:")
        for name, share in report.cost_by_component.items():
            lines.append(f"    - {name}: {share}")
    return "\n".join(lines)


def render_confidence_report(report: ConfidenceReport) -> str:
    lines = [
        f"Confidence — run {report.run_id} (workflow={report.workflow})",
        f"  overall: {report.overall:.2f}  → action: {report.recommended_action}",
        "  dimensions:",
    ]
    for name, value in report.dimensions.items():
        lines.append(f"    - {name}: {value:.2f}")
    return "\n".join(lines)


def render_simulation_report(report: SimulationReport) -> str:
    return "\n".join(
        [
            f"Simulation — {report.recommendation}",
            f"  workflow/lane : {report.recommended_workflow} / {report.recommended_lane}",
            f"  confidence    : {report.confidence_estimate:.2f}",
            f"  risk flags    : {', '.join(report.risk_flags) or 'none'}",
            f"  provider calls: {report.provider_calls}",
        ]
    )


def render_profiler_report(report: ProfilerReport) -> str:
    lines = [f"Profiler — run {report.run_id}", "  cost by component:"]
    for name, share in sorted(report.cost_by_component.items(), key=lambda kv: -kv[1]):
        lines.append(f"    - {name}: {share:.1%}")
    lines.append(f"  bottlenecks: {', '.join(report.bottlenecks) or 'none'}")
    for rec in report.recommendations:
        lines.append(f"  • {rec}")
    return "\n".join(lines)


def render_health_report(report: RuntimeHealthReport) -> str:
    measured = len(report.dimensions)
    total = measured + len(report.unmeasured_dimensions)
    lines = [
        f"Runtime health — overall {report.overall_score:.2f} "
        f"({measured}/{total} dimensions measured)",
        "  dimensions:",
    ]
    for name, value in report.dimensions.items():
        marker = " (!)" if value < 0.4 else ""
        lines.append(f"    - {name}: {value:.2f}{marker}")
    for name in report.unmeasured_dimensions:
        lines.append(f"    - {name}: UNMEASURED")
    if report.critical_findings:
        lines.append(f"  critical: {', '.join(report.critical_findings)}")
    for rec in report.recommendations:
        lines.append(f"  • {rec}")
    return "\n".join(lines)


def render_workflow_comparison(comparison: WorkflowComparison) -> str:
    lines = [f"Workflow what-if — chosen: {comparison.chosen} ({comparison.reason})"]
    for wf, est in comparison.estimates.items():
        total = est.estimated_input_tokens + est.estimated_output_tokens
        lines.append(
            f"  - {wf}: ~{total} tokens, ~{est.estimated_duration_s}s, "
            f"confidence {est.confidence:.2f}"
        )
    lines.append("  (advisory; measured/estimated numbers only — no reduction claim)")
    return "\n".join(lines)


def render_benchmark_results(results: list[BenchmarkResult]) -> str:
    lines = ["Benchmark results:"]
    for res in results:
        status = "measured" if res.measured else "NOT MEASURED"
        verdict = "pass" if res.success else "fail"
        lines.append(
            f"  - [{res.suite}] {res.task_id}: {status}/{verdict} "
            f"({res.tokens} tok) — {res.notes}"
        )
    return "\n".join(lines)


__all__ = [
    "render_benchmark_results",
    "render_confidence_report",
    "render_cost_report",
    "render_health_report",
    "render_profiler_report",
    "render_simulation_report",
    "render_workflow_comparison",
    "to_json",
]
