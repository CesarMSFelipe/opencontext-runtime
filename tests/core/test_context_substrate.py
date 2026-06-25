"""Tests for ContextSubstrateReport and ContextSubstrateBuilder."""

from __future__ import annotations

import pydantic
import pytest

from opencontext_core.agentic.context_substrate import (
    ContextSubstrateBuilder,
    ContextSubstrateReport,
)


def test_report_round_trips(tmp_path) -> None:
    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="add health", phase="explore", budget=8000)
    assert isinstance(report, ContextSubstrateReport)
    restored = ContextSubstrateReport.model_validate(report.model_dump())
    assert restored.schema_version == "opencontext.context_substrate.v1"


def test_available_tokens_matches_budget(tmp_path) -> None:
    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="refactor", phase="spec", budget=5000)
    assert report.available_tokens == 5000


def test_pack_hash_is_none_when_builder_absent(tmp_path) -> None:
    # G2: The substrate builder degrades honestly when KG is not indexed:
    # context_pack_hash is None and a warning is recorded in report.warnings.
    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="test", phase="design", budget=4000)
    assert report.context_pack_hash is None
    assert len(report.warnings) > 0


def test_not_indexed_when_no_oc_dir(tmp_path) -> None:
    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="test", phase="explore", budget=8000)
    assert not report.indexed
    assert len(report.warnings) > 0


def test_unknown_field_rejected() -> None:
    with pytest.raises(pydantic.ValidationError):
        ContextSubstrateReport(indexed=True, graph_status="ok", extra_bad_field="oops")  # type: ignore[call-arg]


def test_none_budget_gives_zero_tokens(tmp_path) -> None:
    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="test", phase="archive", budget=None)
    assert report.available_tokens == 0
