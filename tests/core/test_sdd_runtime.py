from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.sdd_runtime import (
    build_sdd_context,
    detect_test_capabilities,
    write_sdd_context,
)


def test_detect_python_testing_capabilities_from_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n[tool.mypy]\n", encoding="utf-8"
    )

    capabilities = detect_test_capabilities(tmp_path)

    names = {item.name for item in capabilities}
    assert "pytest" in names
    assert "ruff-check" in names
    assert "mypy" in names


def test_detect_package_json_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest", "lint": "eslint ."}}),
        encoding="utf-8",
    )

    capabilities = detect_test_capabilities(tmp_path)

    assert ["npm", "run", "test"] in [item.command for item in capabilities]
    assert ["npm", "run", "lint"] in [item.command for item in capabilities]


def test_write_sdd_context_creates_compact_artifacts(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")

    context, written = write_sdd_context(tmp_path, token_budget_per_phase=2500)

    assert context.strict_tdd is True
    assert context.tdd_mode == "ask"
    assert len(written) == 2
    assert (tmp_path / ".opencontext" / "sdd" / "context.json").exists()
    markdown = (tmp_path / ".opencontext" / "sdd" / "testing.md").read_text(encoding="utf-8")
    assert "Strict TDD" in markdown
    assert "pytest" in markdown


def test_build_sdd_context_recommends_harness_when_missing(tmp_path: Path) -> None:
    context = build_sdd_context(tmp_path)

    assert context.strict_tdd is False
    assert any("No test harness" in instruction for instruction in context.instructions)


def test_build_sdd_context_respects_tdd_mode_off(tmp_path: Path) -> None:
    context = build_sdd_context(tmp_path, tdd_mode="off")

    assert context.tdd_mode == "off"
    assert any("TDD is optional" in instruction for instruction in context.instructions)
