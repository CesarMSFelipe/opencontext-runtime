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

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.agents.delegation import DelegationMode, SubAgentDelegate
from opencontext_core.llm.gateway import LLMGateway
from opencontext_core.models.llm import LLMRequest


class ApplyOperation(StrEnum):
    REPLACE_RANGE = "replace_range"
    INSERT_AFTER = "insert_after"
    DELETE_RANGE = "delete_range"
    DELETE_FILE = "delete_file"
    CREATE_FILE = "create_file"


class ApplyEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    operation: ApplyOperation
    start_line: int | None = None
    end_line: int | None = None
    after_line: int | None = None
    content: str = ""
    reason: str = ""
    requirement_refs: list[str] = Field(default_factory=list)
    task_refs: list[str] = Field(default_factory=list)
    # Additive risk marker for the OC Flow productive executor (AVH-015). Default
    # "low" keeps every existing call-site valid; the field is purely descriptive.
    risk: str = "low"


class AppliedEditReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    operation: ApplyOperation
    changed: bool


def apply_edit(root: Path, edit: ApplyEdit) -> AppliedEditReceipt:
    path = (root / edit.path).resolve()
    # Safety: ensure path is under root
    try:
        path.relative_to(root.resolve())
    except ValueError as err:
        raise RuntimeError(f"Path escape attempt: {edit.path}") from err

    if edit.operation == ApplyOperation.CREATE_FILE:
        if path.exists():
            raise RuntimeError(f"Cannot create existing file: {edit.path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(edit.content, encoding="utf-8")
        return AppliedEditReceipt(path=edit.path, operation=edit.operation, changed=True)

    if not path.exists():
        raise RuntimeError(f"File not found: {edit.path}")

    if edit.operation == ApplyOperation.DELETE_FILE:
        path.unlink()
        return AppliedEditReceipt(path=edit.path, operation=edit.operation, changed=True)

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    if edit.operation == ApplyOperation.REPLACE_RANGE:
        if edit.start_line is None or edit.end_line is None:
            raise RuntimeError("replace_range requires start_line and end_line")
        start = edit.start_line - 1  # 1-based to 0-based
        end = edit.end_line  # exclusive
        new_content = edit.content if edit.content.endswith("\n") else edit.content + "\n"
        new_lines = [*lines[:start], new_content, *lines[end:]]

    elif edit.operation == ApplyOperation.INSERT_AFTER:
        if edit.after_line is None:
            raise RuntimeError("insert_after requires after_line")
        idx = edit.after_line  # insert after line N (1-based) = index N
        new_content = edit.content if edit.content.endswith("\n") else edit.content + "\n"
        new_lines = [*lines[:idx], new_content, *lines[idx:]]

    elif edit.operation == ApplyOperation.DELETE_RANGE:
        if edit.start_line is None or edit.end_line is None:
            raise RuntimeError("delete_range requires start_line and end_line")
        new_lines = lines[: edit.start_line - 1] + lines[edit.end_line :]

    else:
        raise RuntimeError(f"Unsupported operation: {edit.operation}")

    path.write_text("".join(new_lines), encoding="utf-8")
    return AppliedEditReceipt(path=edit.path, operation=edit.operation, changed=True)


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
    """Compose a provider-neutral prompt for a phase from the run context.

    Includes the verified context pack built in the explore phase when present, so
    the model works from OpenContext's retrieved evidence — not just the bare task.
    """
    instruction = _PHASE_INSTRUCTIONS.get(phase, f"Execute the {phase} phase for the task below.")
    task = context.get("task", "")
    pack = (context.get("context") or "").strip()
    parts = [instruction, f"\nTask: {task}", f"Phase: {phase}"]
    if pack:
        parts.append(f"\n## Verified context\n{pack}")
    return "\n".join(parts)


def _phase_handler(gateway: LLMGateway, phase: str, provider: str, model: str) -> Any:
    """Create a delegation handler that runs ``phase`` through the gateway.

    The handler adopts the phase's persona (e.g. OC Tester for test phases) as the
    system prompt, so the agent system auto-switches behavior per phase.
    """
    from opencontext_core.personas import persona_for_phase

    persona = persona_for_phase(phase)
    system_prompt = persona.system_prompt if persona else ""

    def _handler(context: dict[str, Any]) -> dict[str, Any]:
        request = LLMRequest(
            prompt=_build_prompt(phase, context),
            system_prompt=system_prompt,
            provider=provider,
            model=model,
            max_output_tokens=4000,
            metadata={"role": "generate", "phase": phase, "persona": persona.id if persona else ""},
        )
        response = gateway.generate(request)
        return {"status": "success", "output": response.content}

    return _handler


_APPLY_INSTRUCTION = (
    "Implement the task below as concrete file edits. Output ONLY a JSON array — "
    "primary shape is ApplyEdit: "
    '{"path":"...","operation":"replace_range|insert_after|delete_range|create_file",'
    '"start_line":1,"end_line":3,"content":"..."}. '
    "Use surgical ApplyEdit operations for changed lines/blocks; do not rewrite "
    'unchanged sections. Legacy whole-file {"path","content"} is only a fallback '
    "when surgical edit is impossible (e.g. heavily restructured content). "
    "No prose, no Markdown fences, nothing outside the array."
)

# The neutrally-named minimal-diff code-generation signal. A short RUNTIME
# instruction pushing the code model toward the SMALLEST working change. It is
# the single source of truth composed into BOTH flow spines' code-gen: the
# harness ``apply`` prompt (``generate_apply_edits`` below) and the OC Flow
# ``mutate`` prompt (``oc_flow.nodes.ProviderBackedNodeExecutor.mutate``, which
# imports this constant). Kept compact — a handful of lines, negligible tokens.
# The sentinel is the leading line, used by tests (and injection guards) to
# detect the signal without matching the full body.
MINIMAL_DIFF_SENTINEL = "Produce the SMALLEST change that makes the task pass."
MINIMAL_DIFF_INSTRUCTION = (
    f"{MINIMAL_DIFF_SENTINEL} "
    "Climb the ladder before adding code: does it need to exist at all (YAGNI)? "
    "reach for the stdlib or an existing symbol before writing new code; one line "
    "before fifty. No speculative abstractions — no interface, factory, or base "
    "class without a second caller today; no boilerplate for later. Delete dead "
    "code you touch. Boring over clever."
)

# Rodaja 5 A: the code model never learned the TDD posture even though both
# spines ENFORCE the gate. ``tdd_codegen_note`` builds ONE short line reflecting
# the resolved ``tdd_mode`` (and, when known, whether a failing test is already
# proven RED) and is composed into BOTH code-gen prompts alongside the
# minimal-diff signal. Additive — negligible tokens; empty for every non-strict
# posture so ``ask``/``off`` prompts are byte-for-byte unchanged.
_TDD_STRICT_RED_PROVEN = (
    "TDD strict: a failing test is already proven RED for this change — write the "
    "minimal code to make it pass, nothing more."
)
_TDD_STRICT_RED_UNKNOWN = (
    "TDD strict: a failing test must drive this change. If a failing test is "
    "already proven RED, write the minimal code to make it pass; if no failing "
    "test exists yet, write the failing test first, then the minimal code."
)


def tdd_codegen_note(tdd_mode: str | None, *, red_proven: bool | None = None) -> str:
    """The short TDD line for the code-gen prompt, or ``""`` when none applies.

    ``strict`` yields a single directive; ``red_proven`` (when known) selects the
    "make it pass" half, otherwise the model is told to write the failing test
    first if none exists. ``ask`` / ``off`` (and anything else) yield ``""`` — the
    posture line is strict-only, so non-strict prompts are unchanged.
    """
    if tdd_mode != "strict":
        return ""
    return _TDD_STRICT_RED_PROVEN if red_proven else _TDD_STRICT_RED_UNKNOWN


def parse_file_edits(text: str) -> list[dict[str, str] | ApplyEdit]:
    """Parse a model response into file-edit objects.

    Returns a mixed list: elements with an ``"operation"`` key are validated
    and returned as :class:`ApplyEdit` objects (dropped on ``ValidationError``);
    legacy ``{"path", "content"}`` elements are returned as plain dicts. The
    two shapes can coexist in the same response — this function is additive.

    Tolerant of surrounding prose / code fences: it scans for the outermost
    JSON array. Returns ``[]`` when nothing parseable is found.
    """
    import json
    import re

    from pydantic import ValidationError

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end <= start:
        return []
    blob = text[start : end + 1]
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        # Smaller models often emit "JSON" with Python triple-quoted content
        # (`"content": """...multi-line..."""`), which is not valid JSON. Re-encode
        # any triple-quoted body as a proper JSON string, then retry once.
        repaired = re.sub(
            r'"""(.*?)"""|\'\'\'(.*?)\'\'\'',
            lambda m: json.dumps(m.group(1) if m.group(1) is not None else m.group(2)),
            blob,
            flags=re.DOTALL,
        )
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError:
            return []
    edits: list[dict[str, str] | ApplyEdit] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        if "operation" in item:
            # ApplyEdit-shaped: validate and include, or drop on error.
            try:
                edits.append(ApplyEdit(**item))
            except (ValidationError, TypeError):
                pass
        else:
            # Legacy whole-file edit: require string path and content.
            path = item.get("path")
            content = item.get("content")
            if isinstance(path, str) and path and isinstance(content, str):
                edits.append({"path": path, "content": content})
    return edits


def generate_apply_edits(
    gateway: LLMGateway, context: dict[str, Any], *, provider: str, model: str
) -> list[dict[str, str] | ApplyEdit]:
    """Ask the model to produce concrete file edits for the apply phase.

    Returns a list of ``{"path","content"}`` dicts (legacy whole-file) or
    :class:`ApplyEdit` objects (surgical) for ApplyPhase to write (it enforces
    forbidden_paths and rolls back on error). The builder persona drives it.
    """
    from opencontext_core.personas import persona_for_phase

    persona = persona_for_phase("apply")
    # Minimal-diff signal FIRST so the economy directive frames the whole request,
    # then the output-format instruction. Additive — a few lines, negligible tokens.
    parts = [MINIMAL_DIFF_INSTRUCTION]
    # Rodaja 5 A: surface the resolved TDD posture to the code model so strict runs
    # know a failing test must drive the change. Empty (and thus skipped) for
    # ask/off, so non-strict prompts are byte-for-byte unchanged.
    tdd_line = tdd_codegen_note(context.get("tdd_mode"), red_proven=context.get("tdd_red_proven"))
    if tdd_line:
        parts.append(tdd_line)
    parts += [_APPLY_INSTRUCTION, f"\nTask: {context.get('task', '')}"]
    pack = (context.get("context") or "").strip()
    if pack:
        parts.append(f"\n## Verified context\n{pack}")
    # Reinforce the apply-phase economy rules (oc-apply-rules) alongside the
    # builder persona. Lazy import avoids a phases<->executor import cycle; the
    # lookup is best-effort and returns "" when nothing matches.
    from opencontext_core.harness.phases import _phase_skill_rules

    apply_rules = _phase_skill_rules("apply")
    if apply_rules:
        parts.append(f"\n{apply_rules}")
    request = LLMRequest(
        prompt="\n".join(parts),
        system_prompt=persona.system_prompt if persona else "",
        provider=provider,
        model=model,
        max_output_tokens=6000,
        metadata={"role": "generate", "phase": "apply", "persona": persona.id if persona else ""},
    )
    return parse_file_edits(gateway.generate(request).content)


def build_phase_executor(
    gateway: LLMGateway | None,
    *,
    provider: str,
    model: str,
    phase_models: dict[str, str] | None = None,
) -> SubAgentDelegate | None:
    """Build a delegate that runs work-producing phases through ``gateway``.

    Returns ``None`` when no real model is available — i.e. ``gateway`` is
    ``None`` or ``provider`` is ``"mock"`` — so the harness falls back to its
    honest planned/executor-absent path rather than faking a successful artifact.

    ``phase_models`` optionally overrides the model per phase (from the active SDD
    profile), so exploration can run a cheap model and design a strong one. A
    phase with no override — or the ``default`` sentinel — uses ``model``.
    """
    if gateway is None or provider == "mock":
        return None

    overrides = phase_models or {}
    delegate = SubAgentDelegate(mode=DelegationMode.LOCAL)
    for phase in WORK_PRODUCING_PHASES:
        chosen = overrides.get(phase) or model
        if chosen == "default":
            chosen = model
        delegate.register_handler(phase, _phase_handler(gateway, phase, provider, chosen))
    return delegate
