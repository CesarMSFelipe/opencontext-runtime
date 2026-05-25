"""SDD CLI contract tests — verify output format of SDD commands."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import create_sample_project, write_config

from opencontext_cli.main import _sdd_deprecated, _sdd_explore, _sdd_flow, _sdd_propose
from opencontext_core.runtime import OpenContextRuntime


def _runtime(tmp_path: Path, project_root: Path) -> OpenContextRuntime:
    return OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage" / "opencontext",
    )


def _sample_runtime(tmp_path: Path) -> tuple[OpenContextRuntime, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    return _runtime(tmp_path, project_root), project_root


class TestSddDeprecation:
    def test_sdd_explore_returns_deprecation_message(self, tmp_path: Path, capsys) -> None:
        runtime, project_root = _sample_runtime(tmp_path)

        _sdd_explore(runtime, "Where is authentication?", str(project_root), 1200)

        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "deprecated"
        assert "explore" in payload["message"]
        assert "harness run" in payload["hint"]

    def test_sdd_propose_returns_deprecation_message(self, tmp_path: Path, capsys) -> None:
        runtime, project_root = _sample_runtime(tmp_path)
        runtime.index_project(project_root)

        _sdd_propose(runtime, "Where is authentication?", str(project_root), 1200)

        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "deprecated"
        assert "propose" in payload["message"]

    def test_sdd_deprecated_emits_json(self, capsys) -> None:
        _sdd_deprecated("explore", "/tmp")
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "deprecated"
        assert "harness run" in payload["hint"]


class TestSddFlow:
    def test_sdd_flow_returns_completed_status(self, tmp_path: Path, capsys) -> None:
        """SDD flow delegates to harness runner and returns completion status."""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        runtime, _project_root = _sample_runtime(tmp_path)

        _sdd_flow(runtime, "test harness flow", str(tmp_path), 6000, budget_mode="off")

        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "completed"
        assert payload["flow"] == "sdd"
        assert payload["run_id"]
        assert payload["run_dir"]
        assert len(payload["phases"]) >= 1
        assert payload["total_gates"] >= 0

    def test_sdd_flow_tdd_context(self, tmp_path: Path, capsys) -> None:
        """SDD flow should detect TDD capabilities."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        runtime, _ = _sample_runtime(tmp_path)

        _sdd_flow(runtime, "test tdd", str(tmp_path), 6000, budget_mode="off")

        payload = json.loads(capsys.readouterr().out)
        assert "strict_tdd" in payload
        assert isinstance(payload["strict_tdd"], bool)
