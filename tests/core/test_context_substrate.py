"""Tests for ContextSubstrateReport and ContextSubstrateBuilder."""

from __future__ import annotations

import sqlite3

import pydantic
import pytest

from opencontext_core.agentic.context_substrate import (
    ContextSubstrateBuilder,
    ContextSubstrateReport,
)


@pytest.fixture(autouse=True)
def _local_storage_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin OPENCONTEXT_STORAGE_MODE=local so resolve_active_storage_path resolves
    tmp_path-relative .storage/opencontext instead of the global user path.

    r13 Wave 1 routed context_substrate.py off the pinned StorageMode.local onto the
    config-driven resolver; without this pin the builder probes the global storage
    dir and the tmp-created SQLite KG is never found (matches the fixture added for
    tests/core/test_substrate_sqlite_index.py in c5d04a1)."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")


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


def test_sqlite_substrate_populates_consistent_token_metrics(tmp_path) -> None:
    db_dir = tmp_path / ".storage" / "opencontext"
    db_dir.mkdir(parents=True)
    conn = sqlite3.connect(db_dir / "context_graph.db")
    conn.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, content_snippet TEXT)")
    conn.execute(
        "INSERT INTO nodes (id, content_snippet) VALUES (?, ?)",
        ("n1", "alpha beta gamma delta"),
    )
    conn.commit()
    conn.close()

    report = ContextSubstrateBuilder(root=tmp_path).build_for_phase(
        task="test", phase="explore", budget=4000
    )

    assert report.context_pack_hash
    assert report.used_tokens > 0
    assert report.selected_tokens >= report.used_tokens
    assert report.baseline_tokens >= report.selected_tokens
    assert report.compressed_tokens == report.used_tokens
