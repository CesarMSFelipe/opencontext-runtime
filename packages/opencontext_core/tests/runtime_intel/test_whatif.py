"""Tests for runtime.intel.whatif — cost-projection what-if comparison."""

from __future__ import annotations

import pytest

from opencontext_core.runtime.intel.whatif import (
    Plan,
    WhatIfAnalysis,
)


def _plan(workflow: str, tokens: int, model: str = "default", duration_s: float = 1.0) -> Plan:
    return Plan(workflow=workflow, tokens=tokens, model=model, duration_s=duration_s)


class TestWhatIfRanking:
    def test_compare_returns_three_sorted_ascending(self) -> None:
        wf = WhatIfAnalysis()
        plans = [
            _plan("sdd", tokens=5000),
            _plan("oc_flow", tokens=2000),
            _plan("quick", tokens=200),
        ]
        result = wf.compare(plans)
        assert len(result) == 3
        costs = [e.cost_usd for e in result]
        assert costs == sorted(costs)

    def test_compare_uses_plan_tokens_and_model(self) -> None:
        wf = WhatIfAnalysis()
        plans = [
            _plan("big", tokens=1000, model="large"),
            _plan("small", tokens=1000, model="small"),
            _plan("default", tokens=1000, model="default"),
        ]
        result = wf.compare(plans)
        # large=0.015, default=0.002, small=0.0005 → sorted asc
        assert [e.workflow for e in result] == ["small", "default", "big"]

    def test_compare_raises_on_fewer_than_three_plans(self) -> None:
        wf = WhatIfAnalysis()
        with pytest.raises(ValueError):
            wf.compare([_plan("a", tokens=10), _plan("b", tokens=20)])


class TestWhatIfImmutability:
    def test_plans_not_mutated(self) -> None:
        wf = WhatIfAnalysis()
        plans = [
            _plan("sdd", tokens=5000),
            _plan("oc_flow", tokens=2000),
            _plan("quick", tokens=200),
        ]
        snapshot = [(p.workflow, p.tokens, p.model) for p in plans]
        wf.compare(plans)
        after = [(p.workflow, p.tokens, p.model) for p in plans]
        assert snapshot == after

    def test_input_list_not_reordered(self) -> None:
        wf = WhatIfAnalysis()
        plans = [
            _plan("sdd", tokens=5000),
            _plan("oc_flow", tokens=2000),
            _plan("quick", tokens=200),
        ]
        order = [p.workflow for p in plans]
        wf.compare(plans)
        assert [p.workflow for p in plans] == order


class TestCostEstimate:
    def test_estimate_has_required_fields(self) -> None:
        wf = WhatIfAnalysis()
        result = wf.compare([_plan("a", tokens=100, model="default", duration_s=2.0),
                             _plan("b", tokens=200, model="default", duration_s=1.0),
                             _plan("c", tokens=300, model="default", duration_s=0.5)])
        est = result[0]
        for field_name in (
            "workflow", "input_tokens", "output_tokens", "tool_calls",
            "duration_s", "cost_usd", "confidence", "assumptions",
        ):
            assert hasattr(est, field_name), f"missing {field_name}"

    def test_confidence_in_unit_interval(self) -> None:
        wf = WhatIfAnalysis()
        plans = [_plan("a", tokens=100), _plan("b", tokens=200), _plan("c", tokens=300)]
        result = wf.compare(plans)
        for est in result:
            assert 0.0 < est.confidence <= 1.0

    def test_assumptions_nonempty(self) -> None:
        wf = WhatIfAnalysis()
        plans = [_plan("a", tokens=100), _plan("b", tokens=200), _plan("c", tokens=300)]
        result = wf.compare(plans)
        assert all(len(est.assumptions) >= 1 for est in result)
