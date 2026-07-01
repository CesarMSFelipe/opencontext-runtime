"""RED tests for the developer-experience metrics dataclass.

Spec: openspec/changes/opencontext-1-0-convergence/specs/developer-experience-onboarding/spec.md
          REQ-dx-onb-001 (first-run journey → time_to_first_context)

``DxMetrics`` is the structured record the wizard and ``opencontext metrics``
emit at the end of a first-run journey. It is intentionally minimal
(time-to-first-context + setup-success-rate) plus a few roll-ups so the
``success-metrics-dashboard`` (PR-R2-G) can consume it without reaching
into wizard internals.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from opencontext_core.onboarding.metrics import DxMetrics


class TestDxMetricsFields:
    def test_default_metrics_have_required_fields(self) -> None:
        m = DxMetrics()
        assert m.time_to_first_context_seconds == 0.0
        assert m.setup_success_rate == 0.0
        assert m.first_run_completed is False
        assert m.indexed_files == 0
        assert m.indexed_symbols == 0

    def test_explicit_construction_records_all_fields(self) -> None:
        m = DxMetrics(
            time_to_first_context_seconds=42.5,
            setup_success_rate=0.95,
            first_run_completed=True,
            indexed_files=10,
            indexed_symbols=137,
            knowledge_graph_nodes=4,
            knowledge_graph_edges=7,
            active_clients=("opencode", "claude-code"),
        )
        assert m.time_to_first_context_seconds == 42.5
        assert m.setup_success_rate == 0.95
        assert m.first_run_completed is True
        assert m.indexed_files == 10
        assert m.indexed_symbols == 137
        assert m.knowledge_graph_nodes == 4
        assert m.knowledge_graph_edges == 7
        assert m.active_clients == ("opencode", "claude-code")


class TestDxMetricsValidation:
    def test_negative_time_to_first_context_rejected(self) -> None:
        with pytest.raises(ValueError):
            DxMetrics(time_to_first_context_seconds=-1.0)

    def test_success_rate_above_one_rejected(self) -> None:
        with pytest.raises(ValueError):
            DxMetrics(setup_success_rate=1.5)

    def test_success_rate_below_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            DxMetrics(setup_success_rate=-0.1)

    def test_success_rate_at_boundaries_accepted(self) -> None:
        # 0.0 and 1.0 are valid endpoints.
        DxMetrics(setup_success_rate=0.0)
        DxMetrics(setup_success_rate=1.0)


class TestDxMetricsSerialization:
    def test_to_dict_round_trips_through_json(self) -> None:
        m = DxMetrics(
            time_to_first_context_seconds=12.5,
            setup_success_rate=1.0,
            first_run_completed=True,
            indexed_files=3,
            indexed_symbols=11,
            active_clients=("opencode",),
        )
        blob = json.dumps(asdict(m))
        restored = DxMetrics(**json.loads(blob))
        assert restored == m

    def test_active_clients_normalised_to_tuple(self) -> None:
        # Lists, tuples, and None all collapse to a tuple (or empty tuple)
        # so downstream consumers don't need to handle three shapes.
        m = DxMetrics(active_clients=["opencode", "claude-code"])  # type: ignore[arg-type]
        assert m.active_clients == ("opencode", "claude-code")

    def test_active_clients_default_is_empty_tuple(self) -> None:
        assert DxMetrics().active_clients == ()
