"""The minimal-diff code-generation signal reaches BOTH flow spines' code-gen.

An internal, ultra-minimal instruction tells the code models to produce the
SMALLEST working change. It is a RUNTIME signal (not only the static Builder
persona), so it must reach:

1. The harness ``apply`` code-gen context — ``agents.executor.generate_apply_edits``
   composes it into the prompt sent to the gateway.
2. The harness ``apply`` executor context via the builtin-skill mechanism —
   ``run_phase_executor(state, 'apply')`` injects the ``minimal-diff`` builtin
   skill's compact rules through the existing ``_phase_skill_rules`` seam.

The OC Flow ``mutate`` reach is covered in ``tests/workflows``.

Naming constraint: the instruction/skill MUST be neutrally named — no persona or
competitor names anywhere in its text (enforced repo-wide by the forbidden-names
guard; asserted focally here too).

Every test is tmp-isolated and model-free: a fake gateway/delegate captures the
prompt the harness built so we can assert on it without any network round-trip.
"""

from __future__ import annotations

from typing import Any

from opencontext_core.agents.executor import (
    MINIMAL_DIFF_INSTRUCTION,
    MINIMAL_DIFF_SENTINEL,
    generate_apply_edits,
)

# Names that must never appear in the minimal-diff instruction/skill text.
_BANNED_NAMES = ("ponytail", "caveman", "gentle-ai", "gentleai", "graphify")


class _CapturingGateway:
    """Deterministic gateway stand-in: records requests, returns an empty edit set.

    Honest — it replaces only the network call; the caller still builds the real
    prompt. Returns ``[]`` (a valid but empty ApplyEdit array) so ``parse_file_edits``
    yields no edits and nothing is written.
    """

    def __init__(self) -> None:
        self.calls: list[Any] = []

    def generate(self, request: Any) -> Any:
        self.calls.append(request)

        class _Resp:
            content = "[]"

        return _Resp()


# --------------------------------------------------------------------------- #
# The instruction constant itself
# --------------------------------------------------------------------------- #


def test_instruction_carries_the_sentinel() -> None:
    """The exported sentinel phrase is a substring of the full instruction."""
    assert MINIMAL_DIFF_SENTINEL
    assert MINIMAL_DIFF_SENTINEL in MINIMAL_DIFF_INSTRUCTION


def test_instruction_is_neutrally_named() -> None:
    """No persona/competitor name appears in the instruction (case-insensitive)."""
    lowered = MINIMAL_DIFF_INSTRUCTION.lower()
    for banned in _BANNED_NAMES:
        assert banned not in lowered, f"banned name {banned!r} leaked into the instruction"


def test_instruction_expresses_the_ladder() -> None:
    """The instruction expresses the smallest-change ladder (substance, not just a label)."""
    lowered = MINIMAL_DIFF_INSTRUCTION.lower()
    assert "smallest" in lowered
    # Climb-the-ladder substance: YAGNI / stdlib-or-existing-symbol / one line before fifty.
    assert "yagni" in lowered or "exist at all" in lowered
    assert "no speculative" in lowered or "speculative abstraction" in lowered


# --------------------------------------------------------------------------- #
# Harness apply code-gen — generate_apply_edits composes the instruction
# --------------------------------------------------------------------------- #


def test_apply_codegen_prompt_carries_minimal_diff_instruction() -> None:
    """generate_apply_edits injects the minimal-diff sentinel into the model prompt."""
    gateway = _CapturingGateway()
    context = {"task": "add a flag", "context": "## Verified context\nPACK"}

    generate_apply_edits(gateway, context, provider="anthropic", model="claude")

    assert gateway.calls, "the gateway was called"
    prompt = gateway.calls[0].prompt
    assert MINIMAL_DIFF_SENTINEL in prompt


def test_apply_codegen_preserves_task_and_pack() -> None:
    """The minimal-diff signal is ADDITIVE — task + verified pack survive."""
    gateway = _CapturingGateway()
    context = {"task": "add a flag", "context": "PACK-BODY"}

    generate_apply_edits(gateway, context, provider="anthropic", model="claude")

    prompt = gateway.calls[0].prompt
    assert "add a flag" in prompt
    assert "PACK-BODY" in prompt
    assert MINIMAL_DIFF_SENTINEL in prompt


# --------------------------------------------------------------------------- #
# Harness apply executor context — builtin-skill route (run_phase_executor)
# --------------------------------------------------------------------------- #


def test_apply_phase_executor_injects_minimal_diff_skill() -> None:
    """run_phase_executor(state, 'apply') injects the minimal-diff builtin skill.

    The idiomatic builtin-skill seam (``_phase_skill_rules('apply')``) must surface
    the neutrally-named ``minimal-diff`` skill alongside the existing apply rules.
    """
    import opencontext_core.harness.phases as phases_mod

    # Reset the module-level builtin-registry cache so the new skill is discovered.
    phases_mod._BUILTIN_SKILL_REGISTRY = None
    phases_mod._BUILTIN_SKILL_REGISTRY_BUILT = False

    class _CapturingDelegate:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def delegate(self, phase: str, context: dict[str, Any]) -> Any:
            self.calls.append({"phase": phase, "context": dict(context)})

            class _Result:
                status = "success"
                output = "EDITS"

            return _Result()

    class _FakeState:
        def __init__(self, delegate: Any) -> None:
            self.delegate = delegate
            self.task = "add a flag"
            self.run_id = "r1"
            self.root = "/tmp/proj"
            self.prior_artifact = ""
            self.context_pack = "PACK"

    delegate = _CapturingDelegate()
    phases_mod.run_phase_executor(_FakeState(delegate), "apply")

    ctx = delegate.calls[0]["context"]["context"]
    assert "## Applicable skills" in ctx
    assert "minimal-diff" in ctx
    # The pre-existing apply rules must survive alongside the new skill.
    assert "oc-apply-rules" in ctx


def test_minimal_diff_skill_text_is_neutrally_named() -> None:
    """The minimal-diff builtin skill's rendered rules carry no banned name."""
    import opencontext_core.harness.phases as phases_mod

    phases_mod._BUILTIN_SKILL_REGISTRY = None
    phases_mod._BUILTIN_SKILL_REGISTRY_BUILT = False

    rules = phases_mod._phase_skill_rules("apply", max_skills=5)
    assert "minimal-diff" in rules
    lowered = rules.lower()
    for banned in _BANNED_NAMES:
        assert banned not in lowered, f"banned name {banned!r} leaked into apply skill rules"
