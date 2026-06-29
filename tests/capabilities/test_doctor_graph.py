"""opencontext doctor materialises the Capability Graph (CP-006)."""

from __future__ import annotations

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.doctor.checks import run_doctor


def _config() -> OpenContextConfig:
    return OpenContextConfig.model_validate(default_config_data())


def test_doctor_includes_capabilities_graph_check() -> None:
    checks = run_doctor(_config())
    by_name = {c.name: c for c in checks}

    assert "capabilities.graph" in by_name
    assert "Capability graph" in by_name["capabilities.graph"].details


def test_doctor_capability_check_reflects_detected_nodes() -> None:
    # Run from the repo root (pyproject.toml present) so pytest/ruff are detected.
    checks = run_doctor(_config())
    detail = next(c.details for c in checks if c.name == "capabilities.graph")

    assert "pytest" in detail


def test_existing_doctor_checks_preserved() -> None:
    names = {c.name for c in run_doctor(_config())}
    # The pre-PR checks remain present (additive change).
    assert {"security.mode", "llm.provider", "learning.enabled"} <= names
