"""Tests for KGFreshnessChecker (slice 4: kg freshness).

The checker compares the latest source-file mtime (via project_manifest.json +
filesystem/git) against the index timestamp. A stale index returns the stalest
file path; a fresh index returns ``fresh=True``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from opencontext_core.indexing.kg_freshness import KGFreshnessChecker


def _write_manifest(
    root: Path,
    files: list[tuple[str, float]],
    index_ts: float | None,
) -> Path:
    payload = {
        "project_name": "fixture",
        "root": str(root),
        "files": [
            {
                "path": rel,
                "metadata": {"modified_at_epoch": ts},
            }
            for rel, ts in files
        ],
    }
    if index_ts is not None:
        payload["index_timestamp"] = index_ts
    manifest = root / "project_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest


def test_fresh_when_no_file_modified_after_index(tmp_path: Path) -> None:
    index_ts = 1_000.0
    manifest = _write_manifest(
        tmp_path,
        files=[("a.py", 100.0), ("b.py", 500.0)],
        index_ts=index_ts,
    )
    report = KGFreshnessChecker.check(tmp_path, manifest)
    assert report.fresh is True
    assert report.stalest_path is None


def test_stale_when_any_file_modified_after_index(tmp_path: Path) -> None:
    index_ts = 1_000.0
    manifest = _write_manifest(
        tmp_path,
        files=[("a.py", 100.0), ("b.py", 9_999.0), ("c.py", 500.0)],
        index_ts=index_ts,
    )
    report = KGFreshnessChecker.check(tmp_path, manifest)
    assert report.fresh is False
    assert report.stalest_path == "b.py"
    assert report.stalest_age_s is not None and report.stalest_age_s > 0


def test_fresh_when_index_timestamp_missing_uses_oldest_file(tmp_path: Path) -> None:
    """Without an index timestamp, treat the oldest file mtime as the baseline."""
    manifest = _write_manifest(
        tmp_path,
        files=[("a.py", 100.0), ("b.py", 500.0)],
        index_ts=None,
    )
    report = KGFreshnessChecker.check(tmp_path, manifest)
    # b.py is newer than a.py → stale.
    assert report.fresh is False
    assert report.stalest_path == "b.py"


def test_check_does_not_raise_on_empty_manifest(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, files=[], index_ts=time.time())
    report = KGFreshnessChecker.check(tmp_path, manifest)
    assert report.fresh is True
    assert report.stalest_path is None