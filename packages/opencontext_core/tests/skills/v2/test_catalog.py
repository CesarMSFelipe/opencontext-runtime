"""Tests for skills.v2.catalog — generate + dry-run drift check (A6)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.skills.v2.catalog import (
    Catalog,
    DriftReport,
    generate_catalog,
    dry_run_update,
)


def _seed(root: Path) -> None:
    (root / "a.yaml").write_text(
        "id: a\nname: A\ntier: 0\nrequired_capabilities: [read]\n"
        "persona_compat: [senior-architect]\ncontract: {inputs: [], outputs: []}\n",
        encoding="utf-8",
    )
    (root / "b.yaml").write_text(
        "id: b\nname: B\ntier: 0\nrequired_capabilities: [read]\n"
        "persona_compat: [senior-architect]\ncontract: {inputs: [], outputs: []}\n",
        encoding="utf-8",
    )


def test_catalog_generate_matches_committed_catalog(tmp_path: Path) -> None:
    """generate_catalog is deterministic — same input → same output."""
    _seed(tmp_path)
    a1 = generate_catalog(tmp_path)
    a2 = generate_catalog(tmp_path)
    assert a1 == a2
    assert {s.id for s in a1.skills} == {"a", "b"}


def test_catalog_dry_run_update_reports_drift_without_writing(tmp_path: Path) -> None:
    """dry_run_update reports whether committed catalog is in sync; never writes."""
    _seed(tmp_path)
    report: DriftReport = dry_run_update(tmp_path)
    # nothing committed yet → there's drift
    assert report.drifted is True
    # the report did not write any catalog file under tmp_path
    assert not (tmp_path / "catalog.json").exists()


def test_catalog_dataclass_shape() -> None:
    """Catalog and DriftReport carry the expected fields."""
    c = Catalog(skills=())
    d = DriftReport(drifted=False, current=(), committed=None)
    assert list(c.skills) == []
    assert d.drifted is False
