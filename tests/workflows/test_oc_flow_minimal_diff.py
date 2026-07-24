"""The minimal-diff code-generation signal reaches the OC Flow ``mutate`` code-gen.

OC Flow does not use the SDD Builder persona, so the smallest-change signal must
be threaded into the ``mutate`` prompt as a RUNTIME instruction. This proves the
provider-backed mutator's prompt carries the neutrally-named minimal-diff sentinel
(the same one the harness apply code-gen carries), while the existing mutate
contract (schema-valid ApplyEdit set, reason + criterion) is unchanged.

Model-free: a capturing gateway records the ``LLMRequest`` so we can assert on the
prompt with no network round-trip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.agents.executor import MINIMAL_DIFF_SENTINEL
from opencontext_core.models.llm import LLMResponse
from opencontext_core.oc_flow.models import ContextEnvelope, TaskContract
from opencontext_core.oc_flow.nodes import ProviderBackedNodeExecutor

_BANNED_NAMES = ("ponytail", "caveman", "gentle-ai", "gentleai", "graphify")

# A schema-valid but empty edit set: the mutator proposes no edits (valid ``[]``).
_EMPTY_EDITS = "[]"


class _CapturingGateway:
    """Records every request, returns a fixed (empty) edit set. Network-free."""

    def __init__(self, content: str = _EMPTY_EDITS) -> None:
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


def test_mutate_prompt_carries_minimal_diff_instruction(tmp_path: Path) -> None:
    """The OC Flow provider-backed mutate prompt carries the minimal-diff sentinel."""
    gateway = _CapturingGateway()
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")

    executor.mutate(_contract(), ContextEnvelope(task="Fix the failing add() test"))

    assert gateway.calls, "the mutate path called the gateway"
    prompt = gateway.calls[0].prompt
    assert MINIMAL_DIFF_SENTINEL in prompt


def test_mutate_prompt_preserves_scope_and_acceptance(tmp_path: Path) -> None:
    """The minimal-diff signal is ADDITIVE — the task scope + acceptance survive."""
    gateway = _CapturingGateway()
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")

    executor.mutate(_contract(), ContextEnvelope(task="Fix the failing add() test"))

    prompt = gateway.calls[0].prompt
    assert "Fix the failing add() test" in prompt
    assert "add returns the sum" in prompt
    assert MINIMAL_DIFF_SENTINEL in prompt


def test_mutate_prompt_is_neutrally_named(tmp_path: Path) -> None:
    """No persona/competitor name leaks into the OC Flow mutate prompt."""
    gateway = _CapturingGateway()
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")

    executor.mutate(_contract(), ContextEnvelope(task="Fix the failing add() test"))

    lowered = gateway.calls[0].prompt.lower()
    for banned in _BANNED_NAMES:
        assert banned not in lowered, f"banned name {banned!r} leaked into the mutate prompt"
