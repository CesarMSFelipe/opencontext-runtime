"""Tests for HarnessRunner v2 memory store injection."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.runner import HarnessRunner


class TestHarnessRunnerV2:
    # NOTE: bare "constructs without crash" smoke was cut — construction is
    # exercised by test_explore_only_run_completes (and every other runner test).

    def test_has_memory_store_attribute(self, tmp_path: Path) -> None:
        runner = HarnessRunner(root=tmp_path)
        assert hasattr(runner, "_memory_store")
        assert runner._memory_store is not None

    def test_explore_only_run_completes(self, tmp_path: Path) -> None:
        """HarnessRunner.run('explore-only', task) completes without crash."""
        import yaml

        from opencontext_core.config import default_config_data

        config_path = tmp_path / "opencontext.yaml"
        data = default_config_data()
        data["project"]["name"] = "runner-v2-test"
        config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

        runner = HarnessRunner(root=tmp_path)
        result = runner.run("explore-only", "test task for runner v2")
        from opencontext_core.harness.models import GateStatus

        # A valid project + explore-only must not FAIL, and must produce artifacts.
        assert result.status is not GateStatus.FAILED
        assert result.artifacts
        assert result.run_id.startswith("explore-only-")
