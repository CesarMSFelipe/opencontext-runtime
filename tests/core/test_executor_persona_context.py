"""The phase executor adopts the phase persona and injects the verified context.

Behavior, captured at the gateway boundary — not implementation details.
"""

from __future__ import annotations

from opencontext_core.agents.executor import build_phase_executor
from opencontext_core.models.llm import LLMRequest, LLMResponse
from opencontext_core.personas import persona_for_phase


class _CapturingGateway:
    """Records the last LLMRequest and returns a canned response."""

    def __init__(self) -> None:
        self.last: LLMRequest | None = None

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.last = request
        return LLMResponse(
            content="ok",
            provider=request.provider,
            model=request.model,
            input_tokens=1,
            output_tokens=1,
        )


def test_phase_persona_mapping_has_tester_for_test_phases() -> None:
    assert persona_for_phase("apply").id == "oc-tester"
    assert persona_for_phase("test").id == "oc-tester"
    assert persona_for_phase("verify").id == "oc-reviewer"
    assert persona_for_phase("spec").id == "oc-orchestrator"


def test_executor_injects_persona_system_prompt_and_context() -> None:
    gw = _CapturingGateway()
    delegate = build_phase_executor(gw, provider="anthropic", model="claude-x")
    assert delegate is not None

    delegate.delegate("spec", {"task": "add login", "context": "### src/auth.py\ndef login(): ..."})

    req = gw.last
    assert req is not None
    # Persona auto-switch: spec runs as the orchestrator.
    assert req.system_prompt == persona_for_phase("spec").system_prompt
    assert req.system_prompt  # non-empty
    # Verified context is fed to the model, not just the bare task.
    assert "src/auth.py" in req.prompt
    assert "add login" in req.prompt


def test_executor_is_none_for_mock_provider() -> None:
    # Unchanged honest behavior: no real model -> no executor (harness scaffolds).
    assert build_phase_executor(_CapturingGateway(), provider="mock", model="mock-llm") is None
    assert build_phase_executor(None, provider="anthropic", model="x") is None
