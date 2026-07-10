"""estimate_naive_tokens — the whole-repo ceiling (NOT the headline baseline).

estimate_included_files_tokens — the honest per-task baseline used by the CLI
demo/pack headline: whole-file tokens of ONLY the files the pack drew from.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.evaluation.telemetry import (
    _bare_source_path,
    estimate_included_files_tokens,
    estimate_naive_tokens,
)


def test_bare_source_path_strips_symbol_suffix_not_windows_drive() -> None:
    # Bare paths and ":line" / ":line:name" symbol suffixes.
    assert _bare_source_path("a.py") == "a.py"
    assert _bare_source_path("a.py:12") == "a.py"
    assert _bare_source_path("a.py:12:my_symbol") == "a.py"
    assert _bare_source_path("/tmp/pkg/a.py:5") == "/tmp/pkg/a.py"
    # A Windows drive-letter colon must NOT be treated as a line suffix (regression:
    # split(":") turned "C:\\proj\\a.py" into "C" and the file was never counted).
    assert _bare_source_path(r"C:\proj\a.py") == r"C:\proj\a.py"
    assert _bare_source_path(r"C:\proj\a.py:12:func") == r"C:\proj\a.py"


class _Item:
    def __init__(self, source: str) -> None:
        self.source = source


class _Pack:
    def __init__(self, included: list[_Item]) -> None:
        self.included = included


def test_counts_source_skips_vendored(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x" * 400, encoding="utf-8")  # ~100 tokens
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "big.js").write_text("y" * 4000, encoding="utf-8")  # skipped
    (tmp_path / "image.png").write_bytes(b"\x00" * 4000)  # non-text, skipped

    tokens = estimate_naive_tokens(tmp_path)
    assert 90 <= tokens <= 110  # only a.py counted


def test_empty_project_returns_at_least_one(tmp_path: Path) -> None:
    assert estimate_naive_tokens(tmp_path) == 1


def test_included_baseline_counts_only_pack_files_not_whole_repo(tmp_path: Path) -> None:
    # The pack drew from a.py only. b.py exists in the repo but is NOT in the pack.
    (tmp_path / "a.py").write_text("x" * 400, encoding="utf-8")  # ~100 tokens
    (tmp_path / "b.py").write_text("y" * 8000, encoding="utf-8")  # ~2000 tokens, NOT packed

    pack = _Pack([_Item("a.py")])
    baseline = estimate_included_files_tokens(tmp_path, pack)
    whole_repo = estimate_naive_tokens(tmp_path)

    # Honest baseline is the packed file whole (~100), NOT the whole repo (~2100).
    assert 90 <= baseline <= 110
    assert whole_repo > baseline * 5  # whole-repo ceiling is far larger
    assert baseline != whole_repo


def test_included_baseline_dedupes_symbol_chunks_of_same_file(tmp_path: Path) -> None:
    # Symbol pack items carry "path:line" / "path:line:name" sources; a file counted
    # once even when several of its symbols are included.
    (tmp_path / "a.py").write_text("x" * 400, encoding="utf-8")  # ~100 tokens

    pack = _Pack([_Item("a.py:10:foo"), _Item("a.py:42:bar"), _Item("a.py")])
    baseline = estimate_included_files_tokens(tmp_path, pack)
    assert 90 <= baseline <= 110  # a.py counted exactly once


def test_included_baseline_handles_absolute_sources(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x" * 400, encoding="utf-8")

    pack = _Pack([_Item(str((tmp_path / "a.py").resolve()))])
    assert 90 <= estimate_included_files_tokens(tmp_path, pack) <= 110


def test_included_baseline_empty_pack_returns_at_least_one(tmp_path: Path) -> None:
    assert estimate_included_files_tokens(tmp_path, _Pack([])) == 1
