"""Unit tests for scripts/audit_release_artifacts.py (RELEASE_CONTRACT hygiene, AC-029).

Pure-logic coverage over synthetic artifacts built with zipfile/tarfile: the
forbidden-entry rules, the sdist root egg-info allowance, and the CLI exit
codes. No real dist/ artifacts are touched.
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

from scripts.audit_release_artifacts import (
    audit_artifact,
    find_offenders,
    main,
)


def _make_wheel(path: Path, entries: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for entry in entries:
            zf.writestr(entry, b"x")
    return path


def _make_sdist(path: Path, entries: list[str]) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for entry in entries:
            info = tarfile.TarInfo(entry)
            info.size = 1
            tf.addfile(info, io.BytesIO(b"x"))
    return path


class TestFindOffenders:
    def test_clean_wheel_entries_pass(self) -> None:
        entries = [
            "opencontext_core/__init__.py",
            "opencontext_core/store/schema.sql",
            "opencontext_core-1.7.0.dist-info/METADATA",
        ]
        assert find_offenders(entries) == []

    def test_forbidden_directory_segments_are_flagged(self) -> None:
        for segment in (
            ".git",
            ".venv",
            "venv",
            ".ci-venv",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".opencontext",
            ".storage",
            "logs",
        ):
            entry = f"opencontext_core/{segment}/leak.txt"
            assert find_offenders([entry]) == [entry], segment

    def test_coverage_and_log_files_are_flagged(self) -> None:
        offenders = find_offenders(
            [
                ".coverage",
                "pkg/.coverage.host.123",
                "pkg/debug.log",
                "pkg/changelog.md",  # not a .log file
            ]
        )
        assert offenders == [".coverage", "pkg/.coverage.host.123", "pkg/debug.log"]

    def test_segment_match_is_exact_not_substring(self) -> None:
        # .gitignore / convenv are NOT .git / venv leaks.
        entries = ["pkg/.gitignore", "pkg/convenv/mod.py", "pkg/venvutil.py"]
        assert find_offenders(entries) == []

    def test_egg_info_is_flagged_in_wheels(self) -> None:
        entry = "opencontext_core.egg-info/PKG-INFO"
        assert find_offenders([entry]) == [entry]

    def test_sdist_root_egg_info_is_allowed_but_nested_is_not(self) -> None:
        root_meta = "opencontext_core-1.7.0/opencontext_core.egg-info/PKG-INFO"
        nested = "opencontext_core-1.7.0/src/stray.egg-info/PKG-INFO"
        assert find_offenders([root_meta], allow_root_egg_info=True) == []
        assert find_offenders([nested], allow_root_egg_info=True) == [nested]


class TestAuditArtifact:
    def test_bad_wheel_reports_offenders(self, tmp_path: Path) -> None:
        wheel = _make_wheel(
            tmp_path / "pkg-1.0-py3-none-any.whl",
            [
                "pkg/__init__.py",
                "pkg/__pycache__/mod.cpython-312.pyc",
                ".opencontext/runs/run.json",
            ],
        )
        offenders = audit_artifact(wheel)
        assert offenders == [
            "pkg/__pycache__/mod.cpython-312.pyc",
            ".opencontext/runs/run.json",
        ]

    def test_clean_sdist_with_root_egg_info_passes(self, tmp_path: Path) -> None:
        sdist = _make_sdist(
            tmp_path / "pkg-1.0.tar.gz",
            [
                "pkg-1.0/pyproject.toml",
                "pkg-1.0/pkg/__init__.py",
                "pkg-1.0/pkg.egg-info/PKG-INFO",
            ],
        )
        assert audit_artifact(sdist) == []

    def test_pyz_is_audited_as_zip(self, tmp_path: Path) -> None:
        pyz = _make_wheel(tmp_path / "opencontext.pyz", ["__main__.py", ".venv/lib/x.py"])
        assert audit_artifact(pyz) == [".venv/lib/x.py"]


class TestMain:
    def test_exits_zero_for_clean_artifacts(self, tmp_path: Path) -> None:
        _make_wheel(tmp_path / "ok-1.0-py3-none-any.whl", ["pkg/__init__.py"])
        assert main([str(tmp_path / "ok-1.0-py3-none-any.whl")]) == 0

    def test_exits_nonzero_listing_offenders(self, tmp_path: Path, capsys) -> None:
        bad = _make_wheel(
            tmp_path / "bad-1.0-py3-none-any.whl",
            ["pkg/__init__.py", "pkg/.pytest_cache/v/cache"],
        )
        assert main([str(bad)]) == 1
        out = capsys.readouterr().out
        assert "pkg/.pytest_cache/v/cache" in out

    def test_exits_nonzero_when_no_artifacts_found(self, tmp_path: Path) -> None:
        assert main([str(tmp_path / "missing.whl")]) == 2
