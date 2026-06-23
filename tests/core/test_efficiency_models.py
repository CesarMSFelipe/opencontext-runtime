"""Tests for the efficiency-benchmark result models (CON vs SIN cost triples).

These models carry the honest, symmetric cost of context-building WITH OpenContext
(CON) vs a realistic OpenContext-free control (SIN). They must:

* be ``extra="forbid"`` (no field rides in silently);
* carry NO "X% reduction"/badge/claim field — numbers only;
* aggregate per-case deltas (median tokens, median tool-calls, latency p50/p95,
  and the count of parity-insufficient cases).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.evaluation.models import (
    CostTriple,
    EfficiencyCaseResult,
    EfficiencyReport,
)


def _triple(tokens: int, tool_calls: int, latency_ms: float) -> CostTriple:
    return CostTriple(tokens=tokens, tool_calls=tool_calls, latency_ms=latency_ms)


def _case(
    case_id: str,
    con: CostTriple,
    sin: CostTriple,
    *,
    sufficient: bool = True,
    difficulty: str | None = None,
    ceiling: int | None = None,
) -> EfficiencyCaseResult:
    return EfficiencyCaseResult(
        case_id=case_id,
        difficulty=difficulty,
        con=con,
        sin=sin,
        ceiling_tokens=ceiling,
        con_sufficient=sufficient,
        source_coverage=1.0 if sufficient else 0.0,
        forbidden_hits=[],
        reasons=[],
    )


class TestCostTriple:
    def test_has_three_symmetric_fields(self) -> None:
        triple = _triple(100, 3, 12.5)
        assert triple.tokens == 100
        assert triple.tool_calls == 3
        assert triple.latency_ms == 12.5

    def test_forbids_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            CostTriple(tokens=1, tool_calls=1, latency_ms=1.0, claim="50% fewer")  # type: ignore[call-arg]

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            CostTriple(tokens=-1, tool_calls=1, latency_ms=1.0)


class TestEfficiencyCaseResult:
    def test_embeds_parity_and_cost(self) -> None:
        result = _case("c1", _triple(100, 1, 5.0), _triple(900, 7, 30.0))
        assert result.con.tool_calls == 1
        assert result.sin.tokens == 900
        assert result.con_sufficient is True

    def test_forbids_claim_field(self) -> None:
        with pytest.raises(ValidationError):
            EfficiencyCaseResult(
                case_id="c1",
                difficulty=None,
                con=_triple(1, 1, 1.0),
                sin=_triple(1, 1, 1.0),
                ceiling_tokens=None,
                con_sufficient=True,
                source_coverage=1.0,
                forbidden_hits=[],
                reasons=[],
                reduction_pct=42.0,  # type: ignore[call-arg]
            )


class TestEfficiencyReport:
    def test_aggregates_median_deltas_and_latency_percentiles(self) -> None:
        report = EfficiencyReport(
            cases=[
                _case("a", _triple(100, 1, 10.0), _triple(900, 5, 40.0)),
                _case("b", _triple(200, 1, 20.0), _triple(600, 4, 50.0)),
                _case("c", _triple(300, 1, 30.0), _triple(300, 3, 60.0)),
            ]
        )
        # per-case token deltas: 800, 400, 0  -> median 400
        assert report.median_token_delta == 400
        # per-case tool-call deltas: 4, 3, 2 -> median 3
        assert report.median_tool_call_delta == 3
        # latency percentiles are computed (non-negative, p95 >= p50)
        assert report.con_latency_p(95) >= report.con_latency_p(50) >= 0.0
        assert report.sin_latency_p(95) >= report.sin_latency_p(50) >= 0.0
        assert report.insufficient_cases == 0

    def test_counts_insufficient_cases(self) -> None:
        report = EfficiencyReport(
            cases=[
                _case("a", _triple(100, 1, 10.0), _triple(900, 5, 40.0), sufficient=True),
                _case("b", _triple(200, 1, 20.0), _triple(600, 4, 50.0), sufficient=False),
            ]
        )
        assert report.insufficient_cases == 1
        assert report.all_sufficient is False

    def test_forbids_claim_field(self) -> None:
        with pytest.raises(ValidationError):
            EfficiencyReport(cases=[], headline_reduction="60%")  # type: ignore[call-arg]

    def test_empty_report_is_well_defined(self) -> None:
        report = EfficiencyReport(cases=[])
        assert report.median_token_delta == 0
        assert report.median_tool_call_delta == 0
        assert report.insufficient_cases == 0
        assert report.all_sufficient is True
