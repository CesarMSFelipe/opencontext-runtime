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


def test_phase_persona_mapping() -> None:
    assert persona_for_phase("explore").id == "oc-explorer"
    assert persona_for_phase("design").id == "oc-architect"
    assert persona_for_phase("apply").id == "oc-builder"
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


def test_persona_models_resolve_to_their_phases(tmp_path) -> None:
    """A model pinned to a persona reaches every phase that persona drives."""
    import yaml

    from opencontext_core.config import default_config_data
    from opencontext_core.harness.runner import HarnessRunner

    data = default_config_data()
    data["sdd"]["persona_models"] = {"oc-orchestrator": "opus", "oc-architect": "haiku"}
    (tmp_path / "opencontext.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")

    phase_models = HarnessRunner(root=tmp_path)._phase_model_map()

    # Orchestrator drives propose/spec/tasks -> all opus.
    assert phase_models["propose"] == "opus"
    assert phase_models["spec"] == "opus"
    assert phase_models["tasks"] == "opus"
    # Architect drives design -> haiku.
    assert phase_models["design"] == "haiku"
    # Builder (apply) has no override and there is no SDD profile here -> absent.
    assert "apply" not in phase_models
