"""Tests for the diagnostic aggregator (T2.31 + extends REQ-OMT-018).

Per strict-TDD: this file is the source of truth for the
``opencontext_memory.diagnostic`` contract. PR2.c.ii shipped
``tools/mem_doctor`` with the 3-check surface (size / conflicts /
retention). PR2.d adds the 4th check (lifecycle) by extracting the
4-check aggregator into ``diagnostic.py``; the tool wrapper delegates to
it. The existing PR2.c.ii assertion (``assert "size" in report.checks``
etc.) keeps passing without modification.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_memory import MemoryStore, Observation
from opencontext_memory.diagnostic import collect_findings


def _make_store(tmp_path) -> MemoryStore:
    return MemoryStore.open(tmp_path / "memory.sqlite3")


def test_mem_doctor_aggregates_four_checks(store_db: Path) -> None:
    """All 4 checks (size, conflicts, retention, lifecycle) end up in the report."""
    store = _make_store(store_db)
    for i in range(20):
        store.write(
            Observation(
                session_id="s-1",
                title=f"obs-{i}",
                content=f"body-{i}",
                project="P",
                type="decision",
            )
        )

    report = collect_findings(store)

    assert "size" in report.checks
    assert "conflicts" in report.checks
    assert "retention" in report.checks
    assert "lifecycle" in report.checks  # NEW — PR2.d
    assert report.state == "ok"  # 20 fresh rows → all checks ok


def test_mem_doctor_lifecycle_check_warns_with_stale_rows(store_db: Path) -> None:
    """When a row has ``review_after`` in the past, the lifecycle check warns."""
    store = _make_store(store_db)
    store.write(
        Observation(
            session_id="s-1",
            title="stale",
            content="body",
            project="P",
            type="decision",
            review_after="2000-01-01T00:00:00Z",  # 26 years ago
        )
    )

    report = collect_findings(store)

    assert report.checks["lifecycle"] == "warn"
    assert report.needs_review == 1
    assert report.state == "warn"


def test_mem_doctor_lifecycle_check_ignores_soft_deleted_rows(store_db: Path) -> None:
    """Soft-deleted rows must NOT trip the lifecycle check."""
    from opencontext_memory.tools.mem_delete import mem_delete

    store = _make_store(store_db)
    obs_id = store.write(
        Observation(
            session_id="s-1",
            title="stale-but-deleted",
            content="body",
            project="P",
            type="decision",
            review_after="2000-01-01T00:00:00Z",
        )
    )
    mem_delete(store, observation_id=obs_id)

    report = collect_findings(store)

    assert report.checks["lifecycle"] == "ok"
    assert report.needs_review == 0


def test_mem_doctor_empty_store_reports_ok(store_db: Path) -> None:
    """Empty store — all 4 checks pass, state == 'ok'."""
    store = _make_store(store_db)

    report = collect_findings(store)

    assert report.observations == 0
    assert report.checks == {"size": "ok", "conflicts": "ok", "retention": "ok", "lifecycle": "ok"}
    assert report.state == "ok"
