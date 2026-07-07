"""Gate catalog contract pinning (HARNESS-GATES-13).

The mandatory gate catalog is implemented in code (``OC_FLOW_GATE_IDS`` plus the
named harness gate classes). ``docs/product-contract/GATES_CONTRACT.md`` freezes
that catalog and formally supersedes the aspirational plan gate lists (DOC1
"Gates obligatorias"; DOC2 §8.5 "Gates comunes"). These tests pin doc <-> code
so neither side can drift silently.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from opencontext_core.harness import gates as harness_gates
from opencontext_core.oc_flow.run_bundle import OC_FLOW_GATE_IDS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT_PATH = _REPO_ROOT / "docs" / "product-contract" / "GATES_CONTRACT.md"

#: DOC1 (docs/opencontext_plan_cierre_completo_sdd_tui_config_tests.md,
#: "Gates obligatorias") aspirational gate ids.
_DOC1_PLAN_GATE_IDS = (
    "config_valid",
    "workspace_valid",
    "context_pack_created",
    "kg_available_or_declared_absent",
    "memory_policy_checked",
    "executor_policy_checked",
    "approval_checked",
    "tdd_red_required_if_strict",
    "mutation_required_if_task_requires_change",
    "mutation_detected_if_required",
    "verification_command_executed",
    "verification_passed",
    "json_contract_valid",
    "evidence_complete",
)

#: DOC2 (docs/opencontext_plan_funcional_cierre_y_tests_reales.md §8.5,
#: "Gates comunes") aspirational gate ids.
_DOC2_PLAN_GATE_IDS = (
    "config_valid",
    "workspace_valid",
    "provider_policy_passed",
    "context_pack_created",
    "kg_available_or_explained",
    "memory_available_or_explained",
    "approval_granted_if_required",
    "tdd_red_proven_if_strict",
    "mutation_performed_if_required",
    "verification_executed_if_required",
    "verification_passed_if_required",
    "memory_delta_valid",
    "graph_delta_valid",
    "report_written",
)


def _contract_text() -> str:
    assert _CONTRACT_PATH.is_file(), (
        "docs/product-contract/GATES_CONTRACT.md must exist: it freezes the "
        "mandatory gate catalog that the plans only sketched aspirationally"
    )
    return _CONTRACT_PATH.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """Return the body of the ``## <heading>`` section of the contract."""
    for part in re.split(r"^## ", text, flags=re.MULTILINE):
        if part.startswith(heading):
            return part
    raise AssertionError(f"GATES_CONTRACT.md is missing the section: ## {heading}")


def _fenced_ids(section: str) -> list[str]:
    """Extract gate ids from the first ```text fence inside a section."""
    match = re.search(r"```text\n(.*?)```", section, flags=re.DOTALL)
    assert match, "section must carry its gate catalog in a ```text fence"
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def _harness_named_gate_ids() -> set[str]:
    """Introspect the named gate classes actually shipped in harness/gates.py."""
    ids: set[str] = set()
    for obj in vars(harness_gates).values():
        if (
            inspect.isclass(obj)
            and obj.__module__ == harness_gates.__name__
            and isinstance(getattr(obj, "id", None), str)
            and callable(getattr(obj, "evaluate", None))
        ):
            ids.add(obj.id)
    return ids


def test_contract_freezes_oc_flow_gate_catalog() -> None:
    """HARNESS-GATES-13: GATES_CONTRACT.md freezes the OC Flow mandatory gate
    catalog exactly as implemented — same ids, same persisted order as
    ``OC_FLOW_GATE_IDS`` in oc_flow/run_bundle.py."""
    section = _section(_contract_text(), "OC Flow mandatory gate catalog")
    assert _fenced_ids(section) == list(OC_FLOW_GATE_IDS)


def test_contract_freezes_harness_named_gate_catalog() -> None:
    """HARNESS-GATES-13: GATES_CONTRACT.md freezes the harness named gate
    catalog exactly as implemented by the gate classes in harness/gates.py."""
    section = _section(_contract_text(), "Harness named gate catalog")
    assert set(_fenced_ids(section)) == _harness_named_gate_ids()


def test_every_plan_gate_id_is_mapped_in_contract() -> None:
    """HARNESS-GATES-13: every aspirational plan gate id (DOC1 mandatory gate
    list and DOC2 §8.5 common gates) is explicitly mapped in the contract to a
    real gate or a documented superseding mechanism, so the plan lists are
    formally superseded rather than silently dropped."""
    mapping = _section(_contract_text(), "Plan gate mapping")
    for plan_id in sorted({*_DOC1_PLAN_GATE_IDS, *_DOC2_PLAN_GATE_IDS}):
        assert f"`{plan_id}`" in mapping, (
            f"plan gate id '{plan_id}' has no mapping row in GATES_CONTRACT.md"
        )


def test_contract_states_the_per_gate_evidence_rule() -> None:
    """HARNESS-GATES-13: the contract states the per-gate evidence rule (every
    persisted gate record carries a non-empty message), tying the catalog to
    the HARNESS-CRIT-4 invariant."""
    section = _section(_contract_text(), "Evidence rule")
    assert "non-empty" in section
    assert "message" in section
