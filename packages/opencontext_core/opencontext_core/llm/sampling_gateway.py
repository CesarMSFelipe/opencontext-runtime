"""Use the host agent's selected model via MCP sampling — no provider config.

When OpenContext runs inside an MCP host (Claude Code, Codex, OpenCode, …) that
supports the ``sampling`` capability, the host's *selected* model can answer
generation requests without OpenContext configuring any provider or API key. This
is the preferred way to drive the agentic loop: the model the user already chose
in their agent does the work.

``SamplingGateway`` adapts a host "sampler" callback to the ``LLMGateway``
protocol. The MCP server registers the sampler (``register_host_sampler``) once
it has negotiated the client's sampling capability; gateway resolution then
prefers it over any configured provider. The callback itself — the
``sampling/createMessage`` round-trip over the MCP transport — is supplied by the
server, so this module has no host dependency and is fully testable.
"""

from __future__ import annotations

from collections.abc import Callable

from opencontext_core.models.llm import LLMRequest, LLMResponse

# (system_prompt, user_prompt, max_tokens) -> generated text from the host model.
HostSampler = Callable[[str, str, int], str]

_host_sampler: HostSampler | None = None


def register_host_sampler(sampler: HostSampler | None) -> None:
    """Register (or clear) the active host sampler for this process."""
    global _host_sampler
    _host_sampler = sampler


def get_host_sampler() -> HostSampler | None:
    """Return the active host sampler, or None if not running under a sampling host."""
    return _host_sampler


class SamplingGateway:
    """Adapts a host sampler callback to ``LLMGateway.generate``."""

    def __init__(self, sampler: HostSampler, *, model: str = "host-selected") -> None:
        self._sampler = sampler
        self._model = model

    def generate(self, request: LLMRequest) -> LLMResponse:
        content = self._sampler(request.system_prompt, request.prompt, request.max_output_tokens)
        return LLMResponse(
            content=content,
            provider="host",
            model=request.model or self._model,
            input_tokens=0,  # the host owns tokenization/accounting for its model
            output_tokens=0,
            metadata={"via": "mcp-sampling"},
        )
