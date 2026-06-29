"""Skill lifecycle — resolve → validate inputs → execute → validate output → receipt.

The book (doc 06 — Skill Lifecycle) requires a skill to be a typed procedure: its
declared inputs are validated *before* execution, its outputs validated against the
declared contract *after*, and a receipt emitted referencing the skill and its
outputs. Free-form text is never consumed by the runtime.

Layer L6: imports only L0 (compat) + the L6 skill definition/registry. The executor
is injected by the caller (the runtime supplies the real one in PR-007); this module
owns only the contract enforcement around it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.skills.definition import SkillDefinition
from opencontext_core.skills.registry import SkillNotFound, SkillRegistryV2

SkillExecutor = Callable[[SkillDefinition, dict[str, Any]], dict[str, Any]]


class SkillInputError(ValueError):
    """Raised when a skill is invoked without its declared inputs (pre-execution)."""


class SkillReceipt(BaseModel):
    """Receipt emitted when a skill lifecycle completes (book Skill Lifecycle)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.skill_receipt.v1"
    skill_id: str
    skill_version: str = "1.0"
    status: str = Field(description="done | failed_contract")
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    created_at: str = ""


class SkillRunResult(BaseModel):
    """Result of one skill lifecycle: the validated outputs and the receipt."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str
    status: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    missing_outputs: list[str] = Field(default_factory=list)
    receipt: SkillReceipt


def _now() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


def run_skill(
    skill: SkillDefinition | str,
    inputs: dict[str, Any],
    executor: SkillExecutor,
    *,
    registry: SkillRegistryV2 | None = None,
    receipt_sink: Callable[[SkillReceipt], Any] | None = None,
) -> SkillRunResult:
    """Run one skill through the typed lifecycle.

    1. Resolve the skill (by id via ``registry`` when a string is passed).
    2. Validate declared inputs are present — reject *before* execution.
    3. Execute via the injected ``executor``.
    4. Validate the produced outputs against the declared output contract.
    5. Emit a receipt referencing the skill id and outputs.

    Raises :class:`SkillInputError` at step 2; a missing output at step 4 yields a
    ``failed_contract`` result (returned, not raised, so the runtime can route it).
    """
    defn = _resolve(skill, registry)

    missing_in = defn.missing_inputs(inputs)
    if missing_in:
        raise SkillInputError(f"skill {defn.id!r} missing required inputs: {', '.join(missing_in)}")

    produced = executor(defn, inputs)
    missing_out = defn.missing_outputs(produced)
    status = "failed_contract" if missing_out else "done"

    receipt = SkillReceipt(
        skill_id=defn.id,
        skill_version=defn.version,
        status=status,
        inputs=list(inputs.keys()),
        outputs=list(produced.keys()),
        created_at=_now(),
    )
    if receipt_sink is not None:
        receipt_sink(receipt)

    return SkillRunResult(
        skill_id=defn.id,
        status=status,
        outputs=produced,
        missing_outputs=missing_out,
        receipt=receipt,
    )


def _resolve(skill: SkillDefinition | str, registry: SkillRegistryV2 | None) -> SkillDefinition:
    if isinstance(skill, SkillDefinition):
        return skill
    reg = registry or SkillRegistryV2.with_builtins()
    if not reg.has(skill):
        raise SkillNotFound(f"unknown skill: {skill!r}")
    return reg.get(skill)
