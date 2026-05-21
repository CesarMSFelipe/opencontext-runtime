"""Tests for git context provider."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from opencontext_core.indexing.git_context import GitContextProvider


class TestGitContextProvider:
    """Test git context provider."""

    @pytest.fixture
    def provider(self, tmp_path: Path) -> GitContextProvider:
        """Create provider with mocked git availability."""
        provider = GitContextProvider(tmp_path)
        provider._available = True
        return provider

    def test_not_available(self, tmp_path: Path) -> None:
        """Test provider when git is not available."""
        provider = GitContextProvider(tmp_path)
        assert not provider.available
        assert provider.get_file_info("test.py") is None
        assert provider.get_recent_changes() == []
        assert provider.get_repo_stats() == {"available": False}

    def test_get_file_info(self, provider: GitContextProvider) -> None:
        """Test getting file info."""
        mock_output = "2024-01-15T10:00:00+00:00|Alice\n"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(stdout=mock_output, returncode=0),
                MagicMock(stdout="5\n", returncode=0),
                MagicMock(stdout="10\t5\tfile.py\n", returncode=0),
                MagicMock(stdout="Alice\nBob\nAlice\n", returncode=0),
            ]

            info = provider.get_file_info("file.py")

        assert info is not None
        assert info.path == "file.py"
        assert info.last_author == "Alice"
        assert info.commit_count == 5
        assert info.lines_added == 10
        assert info.lines_removed == 5
        assert info.top_authors == ["Alice", "Bob"]

    def test_get_recent_changes(self, provider: GitContextProvider) -> None:
        """Test getting recent changes."""
        mock_output = (
            "abc123|Alice|2024-01-15T10:00:00+00:00|Fix bug\n"
            "file1.py\n"
            "file2.py\n"
            "def456|Bob|2024-01-14T09:00:00+00:00|Add feature\n"
            "file3.py\n"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
            diffs = provider.get_recent_changes(days=7)

        assert len(diffs) == 2
        assert diffs[0].commit_hash == "abc123"
        assert diffs[0].author == "Alice"
        assert diffs[0].message == "Fix bug"
        assert diffs[0].files_changed == ["file1.py", "file2.py"]

    def test_get_files_changed_in_last_commit(self, provider: GitContextProvider) -> None:
        """Test getting files from last commit."""
        mock_output = "file1.py\nfile2.py\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
            files = provider.get_files_changed_in_last_commit()

        assert files == ["file1.py", "file2.py"]

    def test_enrich_context(self, provider: GitContextProvider) -> None:
        """Test context enrichment."""
        mock_output = "2024-01-15T10:00:00+00:00|Alice\n"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(stdout=mock_output, returncode=0),
                MagicMock(stdout="5\n", returncode=0),
                MagicMock(stdout="10\t5\tfile.py\n", returncode=0),
                MagicMock(stdout="Alice\n", returncode=0),
            ]

            enriched = provider.enrich_context(["file.py"])

        assert "file.py" in enriched
        assert enriched["file.py"]["last_author"] == "Alice"
        assert enriched["file.py"]["commit_count"] == 5

    def test_get_repo_stats(self, provider: GitContextProvider) -> None:
        """Test getting repo stats."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(stdout="100\n", returncode=0),
                MagicMock(stdout="Alice\nBob\nAlice\n", returncode=0),
                MagicMock(stdout="* main\n  dev\n", returncode=0),
            ]

            stats = provider.get_repo_stats()

        assert stats["available"] is True
        assert stats["total_commits"] == 100
        assert stats["contributors"] == 2
        assert stats["branches"] == 2

    def test_get_blame_for_symbol(self, provider: GitContextProvider) -> None:
        """Test getting blame for symbol."""
        mock_output = (
            "author Alice\n"
            "author-time 1705312800\n"
            "summary Fix bug\n"
            "\tdef test():\n"
            "author Bob\n"
            "author-time 1705226400\n"
            "summary Add test\n"
            "\t    pass\n"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
            lines = provider.get_blame_for_symbol("file.py", 1, 2)

        assert len(lines) == 2
        assert lines[0]["author"] == "Alice"
        assert lines[0]["message"] == "Fix bug"
        assert lines[0]["code"] == "def test():"
        assert lines[1]["author"] == "Bob"
