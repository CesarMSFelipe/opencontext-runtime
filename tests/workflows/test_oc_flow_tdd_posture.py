"""The TDD posture reaches the OC Flow ``mutate`` code-gen (Rodaja 5 A).

OC Flow does not use the SDD Builder persona, so — exactly like the minimal-diff
signal — the TDD posture must be threaded into the ``mutate`` prompt as a RUNTIME
instruction. Under a strict-TDD posture the provider-backed mutator's prompt must
carry the same short TDD line the harness apply code-gen carries; ``ask``/``off``
leave the prompt free of it. The RED-proven flag (from the runner's pre-mutation
red evidence) picks which half of the strict line is shown.

``node_mutate`` threads ``ctx.tdd_mode`` / ``ctx.tdd_red_exit_code`` onto the
executor before calling ``mutate`` so the posture flows from the runner all the
way into code-gen. Model-free: a capturing gateway records the prompt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.agents.executor import MINIMAL_DIFF_SENTINEL
from opencontext_core.models.llm import LLMResponse
from opencontext_core.oc_flow.models import ContextEnvelope, Lane, TaskContract
from opencontext_core.oc_flow.nodes import (
    OCFlowContext,
    ProviderBackedNodeExecutor,
    node_mutate,
)

_TDD_SENTINEL = "TDD strict"


class _CapturingGateway:
    def __init__(self, content: str = "[]") -> None:
        self._content = content
        self.calls: list[Any] = []

    def generate(self, request: Any) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(
            content=self._content,
            provider="mock",
            model="stub",
            input_tokens=1,
            output_tokens=1,
        )


def _contract() -> TaskContract:
    return TaskContract(
        scope="Fix the failing add() test",
        acceptance_criteria=["add returns the sum"],
        verification_plan=["run the add() test"],
    )


# --------------------------------------------------------------------------- #
# Direct executor construction: posture in → TDD line in the prompt.
# --------------------------------------------------------------------------- #


def test_mutate_prompt_strict_carries_tdd_line(tmp_path: Path) -> None:
    gateway = _CapturingGateway()
    executor = ProviderBackedNodeExecutor(
        gateway=gateway, root=tmp_path, provider="mock", tdd_mode="strict"
    )

    executor.mutate(_contract(), ContextEnvelope(task="Fix the failing add() test"))

    prompt = gateway.calls[0].prompt
    assert _TDD_SENTINEL in prompt
    # Additive: minimal-diff signal + scope survive alongside the TDD line.
    assert MINIMAL_DIFF_SENTINEL in prompt
    assert "Fix the failing add() test" in prompt


def test_mutate_prompt_off_omits_tdd_line(tmp_path: Path) -> None:
    gateway = _CapturingGateway()
    executor = ProviderBackedNodeExecutor(
        gateway=gateway, root=tmp_path, provider="mock", tdd_mode="off"
    )

    executor.mutate(_contract(), ContextEnvelope(task="Fix the failing add() test"))

    prompt = gateway.calls[0].prompt
    assert _TDD_SENTINEL not in prompt
    assert MINIMAL_DIFF_SENTINEL in prompt


def test_mutate_prompt_default_omits_tdd_line(tmp_path: Path) -> None:
    """The default executor (no tdd_mode passed) leaves the prompt free of the line."""
    gateway = _CapturingGateway()
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")

    executor.mutate(_contract(), ContextEnvelope(task="Fix the failing add() test"))

    assert _TDD_SENTINEL not in gateway.calls[0].prompt


def test_mutate_prompt_strict_red_proven_picks_minimal_code_half(tmp_path: Path) -> None:
    gateway = _CapturingGateway()
    executor = ProviderBackedNodeExecutor(
        gateway=gateway,
        root=tmp_path,
        provider="mock",
        tdd_mode="strict",
        tdd_red_exit_code=1,  # a non-zero pre-mutation exit → RED proven.
    )

    executor.mutate(_contract(), ContextEnvelope(task="Fix the failing add() test"))

    prompt = gateway.calls[0].prompt.lower()
    assert "make it pass" in prompt or "minimal code" in prompt


# --------------------------------------------------------------------------- #
# node_mutate threads the runner posture from ctx onto the executor.
# --------------------------------------------------------------------------- #


def test_node_mutate_threads_posture_from_ctx(tmp_path: Path) -> None:
    """node_mutate copies ctx.tdd_mode / ctx.tdd_red_exit_code onto the executor."""
    gateway = _CapturingGateway()
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")
    contract = _contract()
    ctx = OCFlowContext(
        root=tmp_path,
        artifacts_dir=tmp_path / "artifacts",
        task="Fix the failing add() test",
        lane=Lane.CAREFUL,
        profile=None,
        executor=executor,
        max_attempts=1,
        contract=contract,
        envelope=ContextEnvelope(task="Fix the failing add() test"),
        tdd_mode="strict",
        tdd_red_exit_code=1,
    )

    node_mutate(ctx)

    assert gateway.calls, "node_mutate drove the executor's mutate"
    prompt = gateway.calls[0].prompt.lower()
    assert "tdd strict" in prompt
    assert "make it pass" in prompt or "minimal code" in prompt
