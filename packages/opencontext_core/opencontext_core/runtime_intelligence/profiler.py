"""Runtime Profiler (book §11) — cost-by-component + bottlenecks from a trace.

A read-only reduction over the real :class:`~opencontext_core.models.trace.RuntimeTrace`
``timings_ms`` (and ``token_estimates``). It attributes time to components, ranks
the dominant ones as bottlenecks, and emits plain recommendations. It invents
nothing: an empty trace yields an empty attribution.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.models.intelligence import ProfilerReport
from opencontext_core.models.trace import RuntimeTrace
from opencontext_core.runtime_intelligence import events as ri_events
from opencontext_core.runtime_intelligence import telemetry_layout


class RuntimeProfiler:
    """Profile a completed run into a :class:`ProfilerReport`."""

    def profile(
        self,
        trace: RuntimeTrace,
        *,
        top_n: int = 3,
        root: str | Path = ".",
        emit: bool = False,
    ) -> ProfilerReport:
        """Reduce ``trace.timings_ms`` to component shares + ranked bottlenecks."""
        timings = dict(trace.timings_ms)
        total = sum(timings.values())
        if total <= 0:
            report = ProfilerReport(
                run_id=trace.run_id,
                cost_by_component={},
                bottlenecks=[],
                recommendations=["no timing signal recorded for this run"],
            )
        else:
            by_component = {k: round(v / total, 4) for k, v in timings.items()}
            ranked = sorted(by_component.items(), key=lambda kv: kv[1], reverse=True)
            bottlenecks = [name for name, _ in ranked[:top_n]]
            recommendations = self._recommend(ranked)
            report = ProfilerReport(
                run_id=trace.run_id,
                cost_by_component=by_component,
                bottlenecks=bottlenecks,
                recommendations=recommendations,
            )
        if emit:
            telemetry_layout.append_event(
                ri_events.PROFILER_REPORTED,
                {"run_id": trace.run_id, "bottlenecks": report.bottlenecks},
                root,
            )
        return report

    @staticmethod
    def _recommend(ranked: list[tuple[str, float]]) -> list[str]:
        if not ranked:
            return []
        top_name, top_share = ranked[0]
        recs: list[str] = []
        if top_share >= 0.5:
            recs.append(
                f"'{top_name}' dominates this run ({top_share:.0%} of time) — investigate it first"
            )
        else:
            recs.append(f"top component is '{top_name}' ({top_share:.0%} of time)")
        return recs


__all__ = ["RuntimeProfiler"]
