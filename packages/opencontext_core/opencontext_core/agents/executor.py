"""Gateway-backed executor for the SDD work-producing phases.

Builds a :class:`SubAgentDelegate` whose per-phase handlers call a configured
:class:`~opencontext_core.llm.gateway.LLMGateway`. The harness phases read this
delegate off ``state.delegate`` (via ``run_phase_executor``) and use its output
as the real, completed artifact.

The builder is deliberately conservative about what counts as a usable LLM:
``build_phase_executor`` returns ``None`` for the ``mock`` provider (and when no
gateway resolves), so the harness keeps its honest planned/executor-absent
behavior whenever no real model is configured.
"""

from __future__ import annotations

from typing import Any

from opencontext_core.agents.delegation import DelegationMode, SubAgentDelegate
from opencontext_core.llm.gateway import LLMGateway
from opencontext_core.models.llm import LLMRequest

# Phases that produce an LLM-authored artifact through the delegation seam.
WORK_PRODUCING_PHASES: tuple[str, ...] = ("spec", "design", "tasks")

# Per-phase instruction framing the request sent to the gateway. Provider-neutral.
_PHASE_INSTRUCTIONS: dict[str, str] = {
    "spec": (
        "Write a delta specification for the task below. Use RFC 2119 keywords "
        "(MUST/SHALL/SHOULD) and GIVEN/WHEN/THEN scenarios. Output Markdown only."
    ),
    "design": (
        "Write the technical design for the task below: architecture, components, "
        "files to create or modify, data flow, and testing strategy. Output Markdown only."
    ),
    "tasks": (
        "Break the task below into an ordered list of implementation tasks. Output a "
        "JSON array; each item has id, description, file_paths, and complexity."
    ),
}


def _build_prompt(phase: str, context: dict[str, Any]) -> str:
    """Compose a provider-neutral prompt for a phase from the run context."""
    instruction = _PHASE_INSTRUCTIONS.get(phase, f"Execute the {phase} phase for the task below.")
    task = context.get("task", "")
    return f"{instruction}\n\nTask: {task}\nPhase: {phase}"


def _phase_handler(gateway: LLMGateway, phase: str, provider: str, model: str) -> Any:
    """Create a delegation handler that runs ``phase`` through the gateway."""

    def _handler(context: dict[str, Any]) -> dict[str, Any]:
        request = LLMRequest(
            prompt=_build_prompt(phase, context),
            provider=provider,
            model=model,
            max_output_tokens=4000,
            metadata={"role": "generate", "phase": phase},
        )
        response = gateway.generate(request)
        return {"status": "success", "output": response.content}

    return _handler


def build_phase_executor(
    gateway: LLMGateway | None,
    *,
    provider: str,
    model: str,
) -> SubAgentDelegate | None:
    """Build a delegate that runs work-producing phases through ``gateway``.

    Returns ``None`` when no real model is available — i.e. ``gateway`` is
    ``None`` or ``provider`` is ``"mock"`` — so the harness falls back to its
    honest planned/executor-absent path rather than faking a successful artifact.
    """
    if gateway is None or provider == "mock":
        return None

    delegate = SubAgentDelegate(mode=DelegationMode.LOCAL)
    for phase in WORK_PRODUCING_PHASES:
        delegate.register_handler(phase, _phase_handler(gateway, phase, provider, model))
    return delegate
