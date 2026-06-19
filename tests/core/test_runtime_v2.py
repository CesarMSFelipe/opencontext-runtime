"""Tests for OpenContextRuntime v2 integration — contract planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import OpenContextConfig, default_config_data
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
    def test_build_contract_classifies_a_bug_task(self, tmp_path: Path) -> None:
        """The contract pins the actual classification, not just 'returns something'."""
        runtime = _make_runtime(tmp_path)
        if not runtime._v2_enabled:
            pytest.skip("v2 planning not available in this environment")
        contract = runtime.build_contract("fix the auth login bug")
        assert contract is not None
        assert contract.task_type == "bugfix"  # the classifier's real output
        assert contract.risk_level in {"low", "medium", "high"}

    def test_build_context_pack_still_works(self, tmp_path: Path) -> None:
        """Existing build_context_pack must not regress."""
        runtime = _make_runtime(tmp_path)
        # Index the tmp_path (empty project)
        runtime.index_project(tmp_path)
        pack = runtime.build_context_pack("test query", max_tokens=1000)
        from opencontext_core.models.context import ContextPackResult

        assert isinstance(pack, ContextPackResult)
