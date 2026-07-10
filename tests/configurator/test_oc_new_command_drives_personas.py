"""The ``oc-new`` slash-command body drives per-phase persona spawns + memory.

Workstream STEP 3/4 of ``oc-memory-parity-and-polish``. The ``oc-new`` command
is the native-editor entry point (written verbatim from
``OPENCONTEXT_COMMANDS``). Like the ``oc-new`` SKILL template, its body must tell
the agent to SPAWN each phase's persona subagent (Task tool / ``subagent_type``)
and to prime + save change-scoped memory — not merely "switch to each persona".
"""

from __future__ import annotations

from opencontext_core.configurator.constants import OPENCONTEXT_COMMANDS


def _oc_new_body() -> str:
    for name, _description, body in OPENCONTEXT_COMMANDS:
        if name == "oc-new":
            return body
    raise AssertionError("oc-new command is not registered in OPENCONTEXT_COMMANDS")


def test_oc_new_command_spawns_each_phase_persona() -> None:
    body = _oc_new_body()
    for persona in (
        "oc-explorer",
        "oc-orchestrator",
        "oc-architect",
        "oc-builder",
        "oc-requirements",
        "oc-planner",
        "oc-harness-verifier",
        "oc-archivist",
    ):
        assert f"subagent_type: {persona}" in body, (
            f"oc-new command must spawn the '{persona}' persona subagent"
        )


def test_oc_new_command_no_stale_personas() -> None:
    """spec/tasks/archive must not name oc-orchestrator; verify must not name oc-reviewer."""
    body = _oc_new_body()
    # oc-orchestrator valid for propose — not for spec/tasks/archive/verify
    assert "subagent_type: oc-reviewer" not in body, (
        "verify persona must be oc-harness-verifier, not oc-reviewer"
    )


def test_oc_new_command_uses_the_task_tool() -> None:
    assert "Task tool" in _oc_new_body()


def test_oc_new_command_wires_the_memory_loop() -> None:
    body = _oc_new_body()
    assert "opencontext_memory_context" in body, "oc-new must prime from change memory"
    assert "opencontext_memory_save" in body, "oc-new must save change memory"
    assert "change:<slug>" in body, "oc-new must scope memory to the change"


def test_oc_new_approval_gate_is_an_option_question() -> None:
    """The approval gate must be a selectable option-question, not free text.

    When the flow pauses for approval before writing code it must present the
    decision as SELECTABLE OPTIONS with a custom/'Other' escape (host-aware:
    Claude Code's AskUserQuestion when present) — never a single exact
    free-text string like "reply 'approved'".
    """
    body = _oc_new_body()
    low = body.lower()
    assert "approval" in low, "oc-new must pause for approval before writing code"
    assert "AskUserQuestion" in body, "oc-new approval gate must name AskUserQuestion"
    assert "option" in low, "oc-new approval gate must be presented as options"
