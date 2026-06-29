"""Cost Engine (book §6/§7) — pre-run estimate + estimate-vs-actual report.

A read-only facade that composes the existing measurement substrate
(:class:`~opencontext_core.metrics.MetricsCollector`, the
:class:`~opencontext_core.models.trace.RuntimeTrace` timings, and the honest
whole-project token baseline from
:func:`opencontext_core.evaluation.telemetry.estimate_naive_tokens`) into the book
report family. It NEVER mutates run state; it recommends/records only.

HONESTY (design DEC-8, memory oc-value-eval-2026-06): the what-if comparison and
``token_savings`` attribution carry measured/estimated numbers only — no
fabricated "X% cheaper" reduction badge. The token-savings baseline reuses the
same honest whole-project baseline the efficiency benchmark and ``pack`` use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.context.planning.classifier import TaskClassifier
from opencontext_core.models.intelligence import (
    CostEstimate,
    CostReport,
    WorkflowComparison,
)
from opencontext_core.models.trace import RuntimeTrace
from opencontext_core.runtime_intelligence import events as ri_events
from opencontext_core.runtime_intelligence import telemetry_layout

# Per-workflow base token/tool-call assumptions. These are deliberate, documented
# heuristics for a PRE-run estimate (book §6 "estimate before executing"); they
# are not measured numbers and every estimate records its assumptions + a
# confidence. Live provider latency/cost feeds arrive with PR-012 (book §4/§19).
_WORKFLOW_BASE: dict[str, dict[str, int]] = {
    "oc-flow": {"input": 4000, "tool_calls": 6},
    "sdd": {"input": 14000, "tool_calls": 20},
}
_LANE_MULTIPLIER: dict[str, float] = {"quick": 0.6, "fast": 1.0, "full": 1.6}
_OUTPUT_RATIO = 0.25  # output tokens as a share of input tokens; heuristic.
_SECONDS_PER_TOOL_CALL = 6  # rough wall-clock per tool call (heuristic).


class CostEngine:
    """Recommends and records cost; never mutates. Composes metrics + telemetry."""

    def __init__(self, *, classifier: TaskClassifier | None = None) -> None:
        self._classifier = classifier or TaskClassifier()

    # -- pre-run estimate (book §6) -------------------------------------------

    def estimate(
        self,
        task: str,
        workflow: str = "oc-flow",
        lane: str = "fast",
        *,
        root: str | Path = ".",
        emit: bool = False,
    ) -> CostEstimate:
        """Produce a deterministic pre-run :class:`CostEstimate`."""
        base = _WORKFLOW_BASE.get(workflow, _WORKFLOW_BASE["oc-flow"])
        lane_mult = _LANE_MULTIPLIER.get(lane, 1.0)
        classification = self._classifier.classify(task)

        # Complexity scales the base estimate; longer/riskier tasks cost more.
        risk_mult = {"low": 0.85, "medium": 1.0, "high": 1.25, "critical": 1.5}.get(
            classification.risk_level, 1.0
        )
        length_mult = 1.0 + min(len(task) / 4000.0, 0.5)
        scale = lane_mult * risk_mult * length_mult

        in_tokens = int(base["input"] * scale)
        out_tokens = int(in_tokens * _OUTPUT_RATIO)
        tool_calls = max(1, int(base["tool_calls"] * lane_mult))
        duration_s = tool_calls * _SECONDS_PER_TOOL_CALL

        estimate = CostEstimate(
            workflow=workflow,
            lane=lane,
            estimated_input_tokens=in_tokens,
            estimated_output_tokens=out_tokens,
            estimated_tool_calls=tool_calls,
            estimated_duration_s=duration_s,
            estimated_cost_usd=None,  # provider pricing arrives with PR-012 (honest).
            confidence=round(classification.confidence, 3),
            assumptions=[
                f"workflow_base={workflow}",
                f"lane={lane} (x{lane_mult})",
                f"risk={classification.risk_level} (x{risk_mult})",
                f"task_type={classification.task_type}",
                "heuristic estimate; no live provider metrics (PR-012)",
            ],
        )
        if emit:
            telemetry_layout.append_event(
                ri_events.COST_ESTIMATED,
                {"workflow": workflow, "lane": lane, "estimate": estimate.model_dump(mode="json")},
                root,
            )
        return estimate

    # -- post-run report (book §6) --------------------------------------------

    def report(
        self,
        *,
        session_id: str,
        run_id: str,
        estimate: CostEstimate,
        trace: RuntimeTrace | None = None,
        actual_input_tokens: int | None = None,
        actual_output_tokens: int | None = None,
        actual_tool_calls: int | None = None,
        actual_duration_s: int | None = None,
        metrics: Any = None,
        naive_tokens: int | None = None,
        root: str | Path = ".",
        emit: bool = True,
    ) -> CostReport:
        """Reconcile *estimate* against measured actuals into a book CostReport."""
        in_tokens = self._coalesce(
            actual_input_tokens, _trace_tokens(trace, ("input", "before")), 0
        )
        out_tokens = self._coalesce(
            actual_output_tokens, _trace_tokens(trace, ("output", "after")), 0
        )
        tool_calls = self._coalesce(
            actual_tool_calls,
            len(trace.event_ledger) if trace is not None else None,
            0,
        )
        duration_s = self._coalesce(
            actual_duration_s,
            int(sum(trace.timings_ms.values()) / 1000) if trace is not None else None,
            0,
        )

        # Prefer measured metrics totals when a collector is supplied.
        if metrics is not None and hasattr(metrics, "get_summary"):
            summary = metrics.get_summary()
            if summary.get("total_tokens"):
                measured_total = int(summary["total_tokens"])
                if in_tokens + out_tokens == 0 and measured_total:
                    in_tokens = measured_total

        estimated_total = estimate.estimated_input_tokens + estimate.estimated_output_tokens
        actual_total = in_tokens + out_tokens
        error_pct = (actual_total - estimated_total) / max(estimated_total, 1) * 100.0

        cost_by_component = _cost_by_component(trace, metrics)

        if naive_tokens is None:
            from opencontext_core.evaluation.telemetry import estimate_naive_tokens

            naive_tokens = estimate_naive_tokens(Path(root))
        token_savings = {
            "naive": int(naive_tokens),
            "optimized": actual_total,
            "saved": max(int(naive_tokens) - actual_total, 0),
        }

        report = CostReport(
            session_id=session_id,
            run_id=run_id,
            estimate=estimate,
            actual_input_tokens=in_tokens,
            actual_output_tokens=out_tokens,
            actual_tool_calls=tool_calls,
            actual_duration_s=duration_s,
            estimate_error_pct=round(error_pct, 2),
            cost_by_component=cost_by_component,
            token_savings=token_savings,
        )
        if emit:
            telemetry_layout.append_event(
                ri_events.COST_REPORTED,
                {
                    "session_id": session_id,
                    "run_id": run_id,
                    "estimate_error_pct": report.estimate_error_pct,
                    "actual_total_tokens": actual_total,
                },
                root,
            )
        return report

    # -- what-if comparison (book §7) -----------------------------------------

    def whatif(
        self,
        task: str,
        *,
        lane: str = "fast",
        candidates: tuple[str, ...] = ("oc-flow", "sdd"),
        root: str | Path = ".",
        emit: bool = True,
    ) -> WorkflowComparison:
        """Compare candidate workflows and recommend one (advisory, no reduction badge).

        The comparison is parity-gated in spirit: it reports estimated tokens /
        duration / a confidence per workflow and chooses by a deterministic rule.
        It carries NO fabricated "% cheaper" claim (design DEC-8) and is advisory —
        the Runtime governs the final selection.
        """
        estimates = {wf: self.estimate(task, wf, lane, root=root) for wf in candidates}
        classification = self._classifier.classify(task)

        # Deterministic selection: high-risk/critical or mutation-heavy work
        # justifies the heavier SDD workflow; otherwise prefer the cheaper lane by
        # estimated tokens. No reduction claim — just the rule + the numbers.
        prefer_sdd = classification.risk_level in ("high", "critical") or (
            classification.requires_mutation and "sdd" in estimates
        )
        if prefer_sdd and "sdd" in estimates:
            chosen = "sdd"
            reason = (
                f"risk={classification.risk_level}, requires_mutation="
                f"{classification.requires_mutation}: heavier SDD workflow recommended"
            )
        else:
            chosen = min(
                estimates,
                key=lambda wf: (
                    estimates[wf].estimated_input_tokens + estimates[wf].estimated_output_tokens
                ),
            )
            reason = f"lowest estimated tokens among {list(estimates)}"

        comparison = WorkflowComparison(
            task=task[:200],
            estimates=estimates,
            chosen=chosen,
            reason=reason,
        )
        if emit:
            telemetry_layout.append_receipt(
                ri_events.RECEIPT_WORKFLOW_COMPARISON,
                comparison.model_dump(mode="json"),
                root,
            )
            telemetry_layout.append_event(
                ri_events.COST_ESTIMATED,
                {"task": task[:120], "candidates": list(candidates), "chosen": chosen},
                root,
            )
        return comparison

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _coalesce(*values: int | None) -> int:
        for value in values:
            if value is not None:
                return int(value)
        return 0


def _trace_tokens(trace: RuntimeTrace | None, keys: tuple[str, ...]) -> int | None:
    if trace is None:
        return None
    for key in keys:
        if key in trace.token_estimates:
            return int(trace.token_estimates[key])
    return None


def _cost_by_component(trace: RuntimeTrace | None, metrics: Any) -> dict[str, Any]:
    """Attribute cost by component from real signals (time-share or metric cost).

    Prefers a metrics-collector per-component cost breakdown when available;
    otherwise falls back to trace ``timings_ms`` proportions (a time-based proxy).
    Returns ``{}`` when there is no signal — never an invented attribution.
    """
    if metrics is not None and hasattr(metrics, "cost_by_component"):
        breakdown = metrics.cost_by_component()
        if breakdown:
            return dict(breakdown)
    if trace is not None and trace.timings_ms:
        total = sum(trace.timings_ms.values()) or 1.0
        return {k: round(v / total, 4) for k, v in trace.timings_ms.items()}
    return {}


__all__ = ["CostEngine"]
