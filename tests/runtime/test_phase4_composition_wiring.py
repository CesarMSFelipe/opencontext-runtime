"""Phase 4 subset C — composition root activates the unified ProviderGateway and
the Runtime Intelligence scheduler estimator behind their flags (VDM-004).

Both flags default OFF; this asserts the WIRING, not a default flip:

* ``runtime.gateway_enabled=True`` -> the live ``llm_gateway`` (the object the
  runtime hands to ``WorkflowServices`` in ``ask``) IS the unified
  ``ProviderGateway``; off -> the legacy ``BudgetAwareLLMGateway`` unchanged.
* ``runtime_intelligence_enabled=True`` -> the composed ``RuntimeScheduler``
  carries the ``SchedulerPlanEstimator`` and ``simulate()`` returns RI-backed
  estimates; off -> the typed stub forecast, byte-for-byte unchanged.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from opencontext_core.config import default_config_data
from opencontext_core.providers.gateway import ProviderGateway
from opencontext_core.runtime import BudgetAwareLLMGateway, OpenContextRuntime
from opencontext_core.runtime.scheduler import RuntimeScheduler
from opencontext_core.runtime_intelligence.simulator import SchedulerPlanEstimator

_PLAN = {
    "run_id": "r1",
    "task": "fix the failing auth test",
    "nodes": ["explore", "edit", "verify"],
}


def _runtime(tmp: Path, *, gateway: bool = False, intelligence: bool = False) -> OpenContextRuntime:
    data = default_config_data()
    data["runtime"]["gateway_enabled"] = gateway
    data["runtime_intelligence_enabled"] = intelligence
    cfg = tmp / "opencontext.yaml"
    cfg.write_text(yaml.safe_dump(data), encoding="utf-8")
    return OpenContextRuntime(config_path=str(cfg), storage_path=tmp / ".storage")


# --- Provider Gateway seam ------------------------------------------------- #


def test_gateway_flag_on_binds_unified_gateway_to_live_path() -> None:
    tmp = Path(tempfile.mkdtemp())
    rt = _runtime(tmp, gateway=True)
    # self.llm_gateway is exactly what ask() threads into WorkflowServices, so the
    # live provider call path resolves through the unified ProviderGateway.
    assert isinstance(rt.llm_gateway, ProviderGateway)


def test_gateway_flag_off_keeps_legacy_budget_gateway() -> None:
    tmp = Path(tempfile.mkdtemp())
    rt = _runtime(tmp, gateway=False)
    assert isinstance(rt.llm_gateway, BudgetAwareLLMGateway)


# --- Runtime Intelligence scheduler seam ----------------------------------- #


def test_intelligence_flag_on_injects_estimator_and_ri_backed_simulate() -> None:
    tmp = Path(tempfile.mkdtemp())
    rt = _runtime(tmp, intelligence=True)
    assert isinstance(rt.runtime_scheduler, RuntimeScheduler)
    assert isinstance(rt.runtime_scheduler.estimator, SchedulerPlanEstimator)

    report = rt.runtime_scheduler.simulate(_PLAN)
    assert report.estimator == "runtime_intelligence"
    assert report.estimated_tokens and report.estimated_tokens > 0
    assert report.proposed_path == ["explore", "edit", "verify"]


def test_intelligence_flag_off_uses_stub_simulate_unchanged() -> None:
    tmp = Path(tempfile.mkdtemp())
    rt = _runtime(tmp, intelligence=False)
    # A scheduler is composed either way, but with no estimator the seam stays
    # the typed stub forecast — identical to the pre-wiring behaviour.
    assert isinstance(rt.runtime_scheduler, RuntimeScheduler)
    assert rt.runtime_scheduler.estimator is None

    report = rt.runtime_scheduler.simulate(_PLAN)
    assert report.estimator == "stub"
    assert report.estimated_tokens is None


def test_both_flags_off_is_default_composition() -> None:
    tmp = Path(tempfile.mkdtemp())
    rt = _runtime(tmp)
    assert isinstance(rt.llm_gateway, BudgetAwareLLMGateway)
    assert rt.runtime_scheduler.estimator is None
