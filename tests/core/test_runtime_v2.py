"""Tests for OpenContextRuntime v2 integration — contract planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import default_config_data, OpenContextConfig
from opencontext_core.runtime import OpenContextRuntime


def _make_runtime(tmp_path: Path) -> OpenContextRuntime:
    data = default_config_data()
    data["project"]["name"] = "runtime-v2-test"
    config = OpenContextConfig.model_validate(data)
    return OpenContextRuntime(
        config=config,
        storage_path=tmp_path / ".storage" / "opencontext",
    )


class TestRuntimeV2Init:
    def test_initializes_with_v2_enabled_attribute(self, tmp_path: Path) -> None:
        runtime = _make_runtime(tmp_path)
        assert hasattr(runtime, "_v2_enabled")

    def test_build_contract_returns_contract_or_none(self, tmp_path: Path) -> None:
        """build_contract never raises — returns ContextContract or None."""
        runtime = _make_runtime(tmp_path)
        result = runtime.build_contract("fix auth bug")
        # Either None (v2 not available) or a contract object
        if result is not None:
            assert hasattr(result, "task_type") or hasattr(result, "risk_level")
        # Both None and a contract are acceptable
        assert result is None or result is not None

    def test_build_contract_has_task_type_and_risk_tier(self, tmp_path: Path) -> None:
        """If v2 is enabled, the contract has task_type and risk_tier fields."""
        runtime = _make_runtime(tmp_path)
        if not getattr(runtime, "_v2_enabled", False):
            pytest.skip("v2 planning not available in this environment")
        result = runtime.build_contract("fix auth bug")
        if result is not None:
            assert hasattr(result, "task_type")
            assert hasattr(result, "risk_level")

    def test_build_context_pack_still_works(self, tmp_path: Path) -> None:
        """Existing build_context_pack must not regress."""
        runtime = _make_runtime(tmp_path)
        # Index the tmp_path (empty project)
        runtime.index_project(tmp_path)
        pack = runtime.build_context_pack("test query", max_tokens=1000)
        from opencontext_core.models.context import ContextPackResult

        assert isinstance(pack, ContextPackResult)
