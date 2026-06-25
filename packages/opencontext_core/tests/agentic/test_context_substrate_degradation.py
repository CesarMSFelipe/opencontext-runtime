"""Tests for context substrate hash and degraded-mode behaviour (TASK-004)."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.agentic.context_substrate import (
    ContextSubstrateBuilder,
)


def test_build_for_phase_no_kg_sets_no_kg_reason(tmp_path: Path) -> None:
    """TASK-004: when KG is absent, no_kg_reason is populated and hash is None."""
    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="test-task", phase="explore", budget=8000)
    assert report is not None
    assert report.context_pack_hash is None
    assert report.no_kg_reason is not None
    assert "not found" in report.no_kg_reason


def test_build_for_phase_context_pack_hash_is_none_without_kg(tmp_path: Path) -> None:
    """TASK-004: returned substrate has context_pack_hash=None when no KG file."""
    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="test-task", phase="explore", budget=8000)
    assert report.context_pack_hash is None


def test_build_for_phase_used_tokens_is_zero(tmp_path: Path) -> None:
    """TASK-004: used_tokens must be 0 — not a fake estimate."""
    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="test-task", phase="apply", budget=4000)
    assert report.used_tokens == 0
    assert report.available_tokens == 4000


def test_build_for_phase_real_hash_when_kg_present(tmp_path: Path) -> None:
    """TASK-004: when KG exists, context_pack_hash is a sha256 hex digest."""
    oc_dir = tmp_path / ".opencontext"
    oc_dir.mkdir()
    kg = {"nodes": [{"id": "a"}, {"id": "b"}]}
    (oc_dir / "knowledge_graph.json").write_text(json.dumps(kg))

    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="test-task", phase="explore", budget=8000)
    assert report.context_pack_hash is not None
    assert report.context_pack_hash.startswith("sha256:")
    assert report.indexed is True
    assert report.no_kg_reason is None


def test_build_for_phase_hash_is_deterministic(tmp_path: Path) -> None:
    """TASK-004: same KG file produces the same hash on successive calls."""
    oc_dir = tmp_path / ".opencontext"
    oc_dir.mkdir()
    kg = {"nodes": [{"id": "x"}, {"id": "y"}, {"id": "z"}]}
    (oc_dir / "knowledge_graph.json").write_text(json.dumps(kg))

    builder = ContextSubstrateBuilder(root=tmp_path)
    r1 = builder.build_for_phase(task="task-a", phase="design", budget=2000)
    r2 = builder.build_for_phase(task="task-b", phase="apply", budget=4000)
    assert r1.context_pack_hash == r2.context_pack_hash
