"""Runtime Profiler — cost-by-component + bottlenecks from a trace (SPEC-RI-011-13)."""

from __future__ import annotations

from opencontext_core.runtime_intelligence.profiler import RuntimeProfiler


def test_retrieval_dominated_trace_ranks_retrieval_top(make_trace) -> None:
    trace = make_trace(
        timings_ms={"context_retrieval": 800.0, "planning": 100.0, "mutation": 100.0}
    )
    report = RuntimeProfiler().profile(trace)
    # Retrieval is the highest share and the first bottleneck.
    ranked = sorted(report.cost_by_component.items(), key=lambda kv: -kv[1])
    assert ranked[0][0] == "context_retrieval"
    assert report.bottlenecks[0] == "context_retrieval"
    assert report.recommendations


def test_empty_timings_yield_empty_attribution(make_trace) -> None:
    trace = make_trace(timings_ms={})
    report = RuntimeProfiler().profile(trace)
    assert report.cost_by_component == {}
    assert report.bottlenecks == []


def test_shares_sum_to_one(make_trace) -> None:
    trace = make_trace(timings_ms={"a": 300.0, "b": 100.0, "c": 100.0})
    report = RuntimeProfiler().profile(trace)
    assert abs(sum(report.cost_by_component.values()) - 1.0) < 1e-6
