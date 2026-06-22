"""Tests for the learning-orchestrator gate (C1) and its doctor surfacing.

Workstream C1 of ``oc-memory-parity-and-polish``:

- ``config.learning.enabled`` (default ``True``) gates construction of the
  ``LearningOrchestrator`` on the runtime. Default preserves today's behavior
  byte-for-byte (C1-1a); ``enabled = false`` swaps in a no-op stand-in so the
  runtime still starts cleanly and NONE of the ``self.learning.*`` read-sites
  raise ``AttributeError`` (C1-1b / DR2).
- ``opencontext doctor`` (via ``run_doctor(config)``) surfaces
  ``LearningOrchestrator.get_statistics()`` when enabled (C1-2a) and reports a
  disabled state without crashing when off (C1-2b).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from opencontext_core.config import LearningConfig, default_config_data
from opencontext_core.doctor.checks import run_doctor
from opencontext_core.learning.learning_orchestrator import (
    LearningOrchestrator,
    NullLearningOrchestrator,
)
from opencontext_core.runtime import OpenContextRuntime


def _runtime(tmp_path: Path, *, learning_enabled: bool | None = None) -> OpenContextRuntime:
    """Build a runtime from default config, optionally toggling learning.enabled."""

    data = default_config_data()
    data["project"]["name"] = "c1-gate"
    data["project_index"]["root"] = str(tmp_path / "proj")
    (tmp_path / "proj").mkdir(parents=True, exist_ok=True)
    if learning_enabled is not None:
        data["learning"] = {"enabled": learning_enabled}
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return OpenContextRuntime(
        config_path=config_path, storage_path=tmp_path / ".storage" / "opencontext"
    )


class TestLearningConfig:
    def test_default_enabled_true(self) -> None:
        """LearningConfig defaults to enabled (zero behavior change)."""

        assert LearningConfig().enabled is True

    def test_root_config_has_learning_default_on(self) -> None:
        """A default-loaded root config carries learning.enabled == True."""

        from opencontext_core.config import OpenContextConfig

        cfg = OpenContextConfig.model_validate(default_config_data())
        assert cfg.learning.enabled is True


class TestNullLearningOrchestrator:
    def test_noop_surface_matches_calls(self, tmp_path: Path) -> None:
        """The Null stand-in answers every method the runtime read-sites use."""

        null = NullLearningOrchestrator()
        op_id = null.start_operation("index", ".")
        assert isinstance(op_id, str)
        # finish_operation accepts the same **kwargs the runtime passes, no raise.
        null.finish_operation(
            op_id,
            tokens_used=10,
            files_consulted=1,
            symbols_consulted=2,
            context_items_selected=3,
            context_items_omitted=0,
            success=True,
            metadata={"k": "v"},
        )
        # get_optimized_budget must honor the fallback so budgets stay sane.
        assert null.get_optimized_budget("ask", fallback=4242) == 4242
        # get_statistics returns a dict the doctor can render.
        assert isinstance(null.get_statistics(), dict)


class TestRuntimeGate:
    def test_default_constructs_real_orchestrator(self, tmp_path: Path) -> None:
        """C1-1a: with no override, learning is the real orchestrator."""

        rt = _runtime(tmp_path)
        assert isinstance(rt.learning, LearningOrchestrator)
        assert not isinstance(rt.learning, NullLearningOrchestrator)

    def test_disabled_uses_null_and_starts_cleanly(self, tmp_path: Path) -> None:
        """C1-1b: enabled=false -> Null stand-in; runtime still starts."""

        rt = _runtime(tmp_path, learning_enabled=False)
        assert isinstance(rt.learning, NullLearningOrchestrator)

    def test_disabled_read_sites_do_not_raise(self, tmp_path: Path) -> None:
        """C1-1b / DR2: the self.learning.* read-sites tolerate the disabled case.

        Exercises the exact methods runtime.py calls on self.learning so a
        missing/None attribute would surface as AttributeError here.
        """

        rt = _runtime(tmp_path, learning_enabled=False)
        # get_optimized_budget (build_context_pack / ask path)
        budget = rt.learning.get_optimized_budget(
            "context_pack", fallback=rt.config.context.max_input_tokens
        )
        assert budget == rt.config.context.max_input_tokens
        # start_operation / finish_operation (index / ask / context_pack paths)
        op_id = rt.learning.start_operation("context_pack", "q", tokens_budgeted=budget)
        rt.learning.finish_operation(op_id, tokens_used=0, success=True)
        # record_outcome feed (verify_context path) — passes self.learning through
        from opencontext_core.learning.feed import record_outcome

        out = record_outcome(
            rt.learning,
            operation_type="verify_context",
            query="q",
            outcome="sentinel",
        )
        assert out == "sentinel"


class TestDoctorSurfacing:
    def test_doctor_shows_stats_when_enabled(self, tmp_path: Path) -> None:
        """C1-2a: doctor includes a learning check reporting statistics."""

        cfg = _runtime(tmp_path).config
        checks = run_doctor(cfg)
        learning_checks = [c for c in checks if c.name.startswith("learning")]
        assert learning_checks, "expected a learning.* doctor check"
        check = learning_checks[0]
        assert check.ok is True
        assert "disabled" not in check.details.lower()

    def test_doctor_reports_disabled_without_crash(self, tmp_path: Path) -> None:
        """C1-2b: doctor reports learning disabled, no error, when off."""

        cfg = _runtime(tmp_path, learning_enabled=False).config
        checks = run_doctor(cfg)
        learning_checks = [c for c in checks if c.name.startswith("learning")]
        assert learning_checks, "expected a learning.* doctor check"
        check = learning_checks[0]
        assert check.ok is True
        assert "disabled" in check.details.lower()
