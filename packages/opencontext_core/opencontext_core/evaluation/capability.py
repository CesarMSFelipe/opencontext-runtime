"""Capability scoring — turn one arm's run into a structural capability verdict.

The efficiency benchmark answers "how many tokens?"; this module answers the
orthogonal, equally-important question "did the arm actually DO the load-bearing
things?" — was the context KG-grounded, was impact consulted before editing, did a
TDD gate run, was memory used, was a spec/artifact chain produced, was the result
correct. A token win on an arm that skipped all of these is not a real win.

Two honesty rules keep the matrix from flattering a system that structurally lacks a
capability:

* ``kg_grounding`` is derived from *evidence on the pack itself* —
  ``bool(pack_result.included_sources)`` — never from a self-reported flag. An arm
  that produced no grounded sources cannot claim grounding.
* The control arms lack the two capabilities that REQUIRE a knowledge graph —
  ``kg_grounding`` (grounded sources) and ``impact_consulted`` (call-graph blast
  radius). When the arm name contains ``"GENTLE"`` or ``"SIN"`` those two are FORCED
  to False regardless of ``run_metadata``. The OTHER capabilities are credited
  honestly from ``run_metadata``: a real SDD system like Gentle-AI genuinely has
  portability, memory (Engram), a spec/artifact chain, and a TDD gate, and denying it
  those would be a strawman — OC must win on the capabilities it actually has, not on
  ones the comparison fabricates.
"""

from __future__ import annotations

from collections.abc import Mapping

from opencontext_core.evaluation.multi_arm import CapabilityMatrix

# Arm-name fragments that mark a structurally-limited control (no KG/impact/TDD/…).
_CONTROL_ARM_FRAGMENTS = ("GENTLE", "SIN")


def score_matrix(
    arm_name: str,
    pack_result: object,
    *,
    run_metadata: Mapping[str, object],
) -> CapabilityMatrix:
    """Score one arm's run into a :class:`CapabilityMatrix`.

    ``kg_grounding`` is taken from real evidence on ``pack_result`` (the presence of
    ``included_sources``); every other capability is read from ``run_metadata``
    booleans. For control arms (name contains ``GENTLE``/``SIN``) the six capabilities
    those systems structurally lack are forced to False.
    """
    kg_grounding = bool(getattr(pack_result, "included_sources", []))

    portability = bool(run_metadata.get("portability", False))
    tdd_gate = bool(run_metadata.get("tdd_gate_passed", False))
    impact_consulted = bool(run_metadata.get("impact_consulted", False))
    memory_used = bool(run_metadata.get("memory_used", False))
    spec_artifact = bool(run_metadata.get("spec_artifact", False))
    artifact_chain = bool(run_metadata.get("artifact_chain", False))
    correctness = bool(run_metadata.get("correctness", False))

    if any(fragment in arm_name for fragment in _CONTROL_ARM_FRAGMENTS):
        # Only the two KG-exclusive capabilities are denied: grounded sources and
        # call-graph impact both require a knowledge graph these grep-based systems do
        # not have. Their other capabilities (memory, spec/artifact chain, TDD gate,
        # portability) are credited honestly from run_metadata — see module docstring.
        kg_grounding = False
        impact_consulted = False

    return CapabilityMatrix(
        portability=portability,
        tdd_gate=tdd_gate,
        kg_grounding=kg_grounding,
        impact_consulted=impact_consulted,
        memory_used=memory_used,
        spec_artifact=spec_artifact,
        artifact_chain=artifact_chain,
        correctness=correctness,
    )
