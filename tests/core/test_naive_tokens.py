"""estimate_naive_tokens — the honest 'read the whole project' baseline."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.evaluation.telemetry import estimate_naive_tokens


def test_counts_source_skips_vendored(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x" * 400, encoding="utf-8")  # ~100 tokens
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "big.js").write_text("y" * 4000, encoding="utf-8")  # skipped
    (tmp_path / "image.png").write_bytes(b"\x00" * 4000)  # non-text, skipped

    tokens = estimate_naive_tokens(tmp_path)
    assert 90 <= tokens <= 110  # only a.py counted


def test_empty_project_returns_at_least_one(tmp_path: Path) -> None:
    assert estimate_naive_tokens(tmp_path) == 1
