"""Tests for D3: ContextReceipt, ContextSavingsReport, ContextSubstrateBuilder."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from opencontext_core.context.receipt import ContextReceipt, ContextSavingsReport
from opencontext_core.context.savings import ContextSavingsReport as SavingsFromModule


class TestContextSavingsReportDegradedPath:
    def test_build_without_builder_returns_degraded(self) -> None:
        report = ContextSavingsReport.build()
        assert report.degraded is True
        assert report.estimated_savings_ratio == 0.0
        assert report.tokens_saved == 0

    def test_degraded_no_exception(self) -> None:
        # Must not raise
        report = ContextSavingsReport.build()
        assert report is not None

    def test_degraded_warning_non_empty(self) -> None:
        report = ContextSavingsReport.build()
        assert report.warning

    def test_estimated_savings_ratio_zero_not_none(self) -> None:
        report = ContextSavingsReport.build()
        assert report.estimated_savings_ratio == 0.0
        assert isinstance(report.estimated_savings_ratio, float)


class TestContextReceiptQualityGate:
    def test_gate_passes_on_zero_savings_not_degraded(self) -> None:
        savings = ContextSavingsReport(
            degraded=False,
            warning="",
            tokens_saved=0,
            tokens_without_pack=100,
            estimated_savings_ratio=0.0,
        )
        receipt = ContextReceipt(savings=savings)
        assert receipt.passed_quality_gate() is True

    def test_gate_fails_when_degraded(self) -> None:
        savings = ContextSavingsReport(
            degraded=True,
            warning="builder absent",
            tokens_saved=0,
            tokens_without_pack=0,
            estimated_savings_ratio=0.0,
        )
        receipt = ContextReceipt(savings=savings)
        assert receipt.passed_quality_gate() is False

    def test_gate_fails_when_savings_is_none(self) -> None:
        receipt = ContextReceipt(savings=None)
        assert receipt.passed_quality_gate() is False

    def test_build_degraded_factory(self) -> None:
        receipt = ContextReceipt.build_degraded("test reason")
        assert receipt.savings is not None
        assert receipt.savings.degraded is True
        assert receipt.passed_quality_gate() is False


class TestContextSubstrateBuilderTokens:
    def test_baseline_tokens_populated_with_kg(self) -> None:
        from opencontext_core.context.receipt import ContextSubstrateBuilder

        with tempfile.TemporaryDirectory() as tmp:
            oc_dir = Path(tmp) / ".opencontext"
            oc_dir.mkdir()
            kg_path = oc_dir / "knowledge_graph.json"
            kg_content = {"nodes": [{"id": f"node-{i}"} for i in range(20)]}
            kg_path.write_text(json.dumps(kg_content))

            builder = ContextSubstrateBuilder(root=tmp)
            report = builder.build_for_phase(task="test task", phase="explore", budget=8000)
            assert report.baseline_tokens > 0
            assert report.selected_tokens > 0
            assert report.selected_tokens <= report.baseline_tokens

    def test_baseline_tokens_zero_without_kg(self) -> None:
        from opencontext_core.context.receipt import ContextSubstrateBuilder

        with tempfile.TemporaryDirectory() as tmp:
            builder = ContextSubstrateBuilder(root=tmp)
            report = builder.build_for_phase(task="test task", phase="explore", budget=8000)
            assert report.baseline_tokens == 0


class TestContextReceiptImportStability:
    def test_import_all_from_receipt_module(self) -> None:
        from opencontext_core.context.receipt import (  # noqa: F401
            AgenticReceipt,
            ContextReceipt,
            ContextSavingsReport,
            ContextSubstrateBuilder,
            ContextSubstrateReport,
        )
