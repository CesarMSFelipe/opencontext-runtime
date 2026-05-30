"""CLI smoke tests for `python -m opencontext_cli harness` commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_cli(*args: str, cwd: Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run the opencontext CLI as a subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "opencontext_cli", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
    )


class TestHarnessCli:
    def test_harness_help(self) -> None:
        result = _run_cli("harness", "--help")
        assert result.returncode == 0
        # argparse shows description before positional args for subparser --help
        assert "Execute SDD or custom harness workflows" in result.stdout
        assert "{run,list}" in result.stdout or "run" in result.stdout

    def test_harness_run_help(self) -> None:
        result = _run_cli("harness", "run", "--help")
        assert result.returncode == 0
        assert "--workflow" in result.stdout
        assert "sdd" in result.stdout
        assert "explore-only" in result.stdout
        assert "apply-only" in result.stdout

    def test_harness_list(self) -> None:
        result = _run_cli("harness", "list")
        assert result.returncode == 0
        assert "sdd" in result.stdout
        assert "explore-only" in result.stdout
        assert "apply-only" in result.stdout

    def test_harness_list_json(self) -> None:
        result = _run_cli("harness", "list", "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "sdd" in data
        assert "explore-only" in data
        assert "apply-only" in data
        assert len(data["sdd"]["phases"]) == 9

    def test_harness_run_explore_only(self, tmp_path: Path) -> None:
        """Run explore-only workflow in a temp directory with pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        result = _run_cli(
            "harness",
            "run",
            "--workflow",
            "explore-only",
            "--task",
            "cli smoke test",
            "--root",
            str(tmp_path),
            "--budget-mode",
            "off",
            timeout=30,
        )
        assert result.returncode == 0
        assert "Harness Run:" in result.stdout
        assert "explore-only" in result.stdout
        assert "explore:" in result.stdout

    def test_harness_run_invalid_workflow(self) -> None:
        result = _run_cli(
            "harness",
            "run",
            "--workflow",
            "nonexistent",
            "--task",
            "test",
            timeout=10,
        )
        assert result.returncode != 0
        # argparse writes parsing errors to stderr
        assert "error:" in result.stderr or "invalid choice" in result.stderr

    def test_harness_run_without_required_args(self) -> None:
        """Missing --task should error."""
        result = _run_cli("harness", "run", "--workflow", "sdd", timeout=10)
        assert result.returncode != 0
        assert "required" in result.stdout.lower() or "required" in result.stderr.lower()

    def test_harness_run_json_output(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        result = _run_cli(
            "harness",
            "run",
            "--workflow",
            "explore-only",
            "--task",
            "json test",
            "--root",
            str(tmp_path),
            "--budget-mode",
            "off",
            "--json",
            timeout=30,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["status"] == "completed"
        assert data["workflow"] == "explore-only"
        assert data["task"] == "json test"
        assert len(data["phases"]) >= 1

    def test_main_module_help(self) -> None:
        """Verify python3 -m opencontext_cli --help works."""
        result = _run_cli("--help", timeout=10)
        assert result.returncode == 0
        assert "harness" in result.stdout
        assert "verify" in result.stdout
        assert "doctor" in result.stdout
