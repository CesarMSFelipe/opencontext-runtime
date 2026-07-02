"""Tests for S1: compression engine wired into substrate build_for_phase.

S1 RED: these fail until CompressionEngine is wired in context_substrate.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.agentic.context_substrate import ContextSubstrateBuilder


def test_build_for_phase_compression_enabled_when_kg_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When KG is indexed and budget is tight, compression fires (compression_enabled=True)."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")

    oc_dir = tmp_path / ".opencontext"
    oc_dir.mkdir()
    # Create a KG with substantial content so the token estimate exceeds a small budget.
    nodes = [{"id": f"node_{i}", "content": f"content {i} " * 20} for i in range(50)]
    kg = {"nodes": nodes}
    (oc_dir / "knowledge_graph.json").write_text(json.dumps(kg))

    builder = ContextSubstrateBuilder(root=tmp_path)
    # Budget 50 tokens < KG size (~2000+) forces the compression engine to fire.
    report = builder.build_for_phase(task="test-task", phase="explore", budget=50)

    assert report.compression_enabled is True, (
        f"Expected compression_enabled=True with tight budget, got {report.compression_enabled}; "
        f"warnings={report.warnings}"
    )


def test_build_for_phase_compression_savings_nonnegative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """compression_savings must be >= 0 (never negative)."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")

    oc_dir = tmp_path / ".opencontext"
    oc_dir.mkdir()
    kg = {"nodes": [{"id": "a"}, {"id": "b"}]}
    (oc_dir / "knowledge_graph.json").write_text(json.dumps(kg))

    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="test-task", phase="apply", budget=8000)

    assert report.compression_savings >= 0, (
        f"compression_savings must be >= 0, got {report.compression_savings}"
    )


def test_build_for_phase_report_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """build_for_phase persists substrate_report.json for sync_state to read."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")

    oc_dir = tmp_path / ".opencontext"
    oc_dir.mkdir()
    kg = {"nodes": [{"id": "x"}]}
    (oc_dir / "knowledge_graph.json").write_text(json.dumps(kg))

    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="test-task", phase="explore", budget=4000)

    # Report must be persisted as JSON
    report_files = list(tmp_path.rglob("substrate_report.json"))
    assert report_files, "substrate_report.json must be written after build_for_phase"

    saved = json.loads(report_files[0].read_text())
    assert saved.get("context_pack_hash") == report.context_pack_hash
    assert "compression_enabled" in saved
    assert "compression_savings" in saved


def test_build_for_phase_compression_disabled_without_kg(tmp_path: Path) -> None:
    """Without KG, compression remains disabled (no side effects on missing index)."""
    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="t", phase="explore", budget=8000)

    assert report.compression_enabled is False
    assert report.context_pack_hash is None
