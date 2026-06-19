"""Per-phase model routing: the active SDD profile picks the model per phase."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from opencontext_core.agents.executor import build_phase_executor
from opencontext_core.harness.runner import HarnessRunner


class _FakeGateway:
    def __init__(self) -> None:
        self.seen: dict[str, str] = {}

    def generate(self, request: Any) -> Any:
        self.seen[request.metadata["phase"]] = request.model
        return SimpleNamespace(content="ok")


def test_executor_routes_model_per_phase() -> None:
    gw = _FakeGateway()
    ex = build_phase_executor(
        gw,
        provider="anthropic",
        model="base-model",
        phase_models={"design": "strong-model", "spec": "default"},
    )
    assert ex is not None
    for phase in ("spec", "design", "tasks"):
        ex.delegate(phase, {"task": "t"})

    assert gw.seen["design"] == "strong-model"  # profile override applied
    assert gw.seen["spec"] == "base-model"  # 'default' sentinel -> base model
    assert gw.seen["tasks"] == "base-model"  # no override -> base model


def test_executor_none_for_mock_or_no_gateway() -> None:
    assert build_phase_executor(None, provider="anthropic", model="m") is None
    assert build_phase_executor(_FakeGateway(), provider="mock", model="m") is None


def test_phase_model_map_reads_active_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opencontext_core import sdd_profiles

    real = sdd_profiles.SDDProfileManager
    monkeypatch.setattr(sdd_profiles, "SDDProfileManager", lambda: real(tmp_path / "profiles"))

    sdd = tmp_path / ".opencontext" / "sdd"
    sdd.mkdir(parents=True)
    (sdd / "context.json").write_text(json.dumps({"sdd_model_profile": "cheap"}), encoding="utf-8")

    mapping = HarnessRunner(root=tmp_path)._phase_model_map()
    assert mapping  # cheap assigns real models per phase
    assert "default" not in mapping.values()  # sentinels are dropped


def test_phase_model_map_empty_without_context(tmp_path: Path) -> None:
    assert HarnessRunner(root=tmp_path)._phase_model_map() == {}


def test_phase_model_map_honors_models_phases_override(tmp_path: Path) -> None:
    """LOW: models.phases overrides were computed into a dead field and never
    applied — they must now reach the per-phase model map."""
    (tmp_path / "opencontext.yaml").write_text(
        "project:\n  name: t\n"
        "models:\n"
        "  default:\n    provider: anthropic\n    model: base\n"
        "  phases:\n    spec:\n      provider: anthropic\n      model: custom-spec\n",
        encoding="utf-8",
    )
    assert HarnessRunner(root=tmp_path)._phase_model_map().get("spec") == "custom-spec"
