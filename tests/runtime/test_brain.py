"""RuntimeBrain tests: 8-kind coverage, receipts, and the no-write-port guard.

Covers RB-002/RB-005/RB-010 and the doc 59 §Brain-restrictions capability
invariant — the Brain only decides; it is constructed with no mutation/tool/
memory ports.
"""

from __future__ import annotations

import inspect

from opencontext_core.agentic.receipt import AgenticReceipt
from opencontext_core.operating_model.performance import ModelRoleRouter
from opencontext_core.personas import persona_for_phase
from opencontext_core.runtime.brain import NullRuntimeBrain, RuntimeBrain
from opencontext_core.runtime.decision_log import DecisionRecorder
from opencontext_core.runtime.decisions import DecisionKind, RuntimeDecision

_CONTEXT = {
    "phase": "design",
    "role": "generate",
    "profile": "enterprise",
    "proposed_node": "apply",
    "current_node": "design",
    "task": "add a security review harness",
}

# Brain-level kinds: the 8 DecisionKind values that RuntimeBrain has strategies
# for.  workflow, memory_promotion, and confidence_report are runner-level
# (emitted by oc_flow/runner.py directly — not brain strategies).
_BRAIN_KINDS = frozenset(DecisionKind) - {
    DecisionKind.workflow,
    DecisionKind.memory_promotion,
    DecisionKind.confidence_report,
}


def test_all_eight_kinds_return_a_runtime_decision() -> None:
    brain = RuntimeBrain()
    for kind in _BRAIN_KINDS:
        decision = brain.decide(kind, _CONTEXT)
        assert isinstance(decision, RuntimeDecision)
        assert decision.kind == kind.value
        assert decision.rationale, f"{kind} produced an empty rationale"


def test_each_decision_emits_an_agentic_receipt_no_new_model() -> None:
    brain = RuntimeBrain()
    for kind in _BRAIN_KINDS:
        decision = brain.decide(kind, _CONTEXT)
        assert decision.receipt_id is not None
        assert decision.receipt_id.startswith("rcpt_")
    assert len(brain.emitted_receipts) == len(_BRAIN_KINDS)
    assert all(isinstance(r, AgenticReceipt) for r in brain.emitted_receipts)
    # The decision links the receipt it emitted (RB-010).
    assert brain.emitted_receipts[-1].trace_id == decision.receipt_id


def test_decision_is_recorded_via_the_record_sink() -> None:
    recorder = DecisionRecorder()
    brain = RuntimeBrain(record=recorder.record)
    brain.decide(DecisionKind.provider, _CONTEXT)
    assert len(recorder.entries()) == 1
    assert recorder.entries()[0].decision.kind == "provider"


def test_default_strategies_preserve_existing_router_outputs() -> None:
    brain = RuntimeBrain()
    # Persona strategy preserves persona_for_phase.
    persona = persona_for_phase("design")
    expected_persona = persona.id if persona is not None else "none"
    assert brain.decide(DecisionKind.persona, {"phase": "design"}).chosen == expected_persona
    # Provider strategy preserves ModelRoleRouter.route_with_budget.
    route = ModelRoleRouter().route_with_budget("generate", "standard")
    assert (
        brain.decide(DecisionKind.provider, {"role": "generate"}).chosen
        == f"{route['provider']}:{route['model']}"
    )


def test_brain_is_deterministic_given_inputs() -> None:
    brain = RuntimeBrain()
    a = brain.decide(DecisionKind.execution_profile, {"profile": "enterprise"})
    b = brain.decide(DecisionKind.execution_profile, {"profile": "enterprise"})
    assert a.chosen == b.chosen
    assert a.reason == b.reason


def test_null_brain_never_recommends() -> None:
    assert NullRuntimeBrain().recommend(run_id="r", runtime_context={"gates": {}}) is None


# --------------------------------------------------------------------- guard
_FORBIDDEN_PORT_PARAMS = {
    "store",
    "session_store",
    "receipt_store",
    "artifact_store",
    "mutator",
    "mutation",
    "tool",
    "tools",
    "toolbox",
    "memory",
    "memory_store",
    "fs",
    "filesystem",
    "harness",
    "harness_runner",
    "executor",
    "writer",
    "apply",
    "command_runner",
}
_ALLOWED_PORT_PARAMS = {"record", "intelligence", "kg", "history"}
_WRITE_VERBS = ("save", "write", "delete", "apply", "mutate", "execute", "run", "put", "edit")


def test_brain_constructor_exposes_no_write_capable_ports() -> None:
    """Structural: the Brain is built only with read ports + a record sink."""
    params = set(inspect.signature(RuntimeBrain.__init__).parameters) - {"self"}
    leaked = params & _FORBIDDEN_PORT_PARAMS
    assert not leaked, f"write-capable port(s): {leaked}"
    extra = params - _ALLOWED_PORT_PARAMS
    assert not extra, f"unexpected ctor params: {extra}"


def test_constructed_brain_has_no_write_capable_dependency() -> None:
    """The only write affordance is the decision ``record`` sink — nothing else."""
    recorder = DecisionRecorder()
    brain = RuntimeBrain(record=recorder.record)
    deps = {
        name: value
        for name, value in vars(brain).items()
        if value is not None and name != "_record" and name != "emitted_receipts"
    }
    for name, dep in deps.items():
        for verb in _WRITE_VERBS:
            assert not callable(getattr(dep, verb, None)), (
                f"Brain dependency {name!r} exposes write method {verb!r}"
            )
