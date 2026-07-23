"""gentle-ai SDD parity, slice 2 — the AGENT asks guided, predefined-option questions.

OpenContext's agent-driven SDD flow must ASK the user with PREDEFINED-OPTION
questions and GUIDE well, mirroring gentle-ai (which does its guiding at the agent
level). The instruction is carried by SHIPPED SOURCE templates that OpenContext
installs, so these tests assert the CONTRACT is present in that source:

* **Proposal question round** - the ``oc-propose`` skill asks 3 to 5 concrete PRODUCT
  questions as predefined-option questions BEFORE writing the proposal, then
  summarizes assumptions and offers accept / revise / second-round. It must NOT ask
  harness mechanics at proposal time, and it must have a non-interactive fallback
  (write a ``## Proposal question round`` section, never hang).
* **Session preflight** — the ``oc-new`` orchestrator entry point reads the handoff's
  ``session_choices`` when present, otherwise asks the four predefined-option groups
  (execution mode / artifact store / delivery / chain), each guided, cached for the
  session, with a non-interactive safe-default fallback.
* **Between-phase gate** — in interactive execution mode the orchestrator pauses,
  summarizes, and asks proceed / adjust / stop (phase-scoped, predefined).

Templates are static markdown shipped verbatim to ``.opencontext/skills/``; the
assertions are on file content. The orchestrator's session-preflight and
between-phase-gate parity live in the orchestrator persona ``system_prompt``
(``personas/__init__.py``), which is rendered verbatim into the installed
``.claude/agents/oc-orchestrator.md`` on install.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TEMPLATES_DIR = (
    REPO_ROOT / "packages" / "opencontext_core" / "opencontext_core" / "skills" / "templates"
)

# Canonical selector values shared with the slice-1 CLI preflight
# (packages/opencontext_cli/.../flow_preflight.py). The agent-level questions MUST
# use these exact values so the guided asking stays consistent across CLI and agent.
ARTIFACT_STORE_VALUES = ("hybrid", "openspec", "engram", "none")
DELIVERY_VALUES = ("ask-on-risk", "single-pr", "auto-chain", "exception-ok", "plan-only")
CHAIN_VALUES = ("stacked-to-main", "feature-branch-chain")
EXECUTION_MODE_VALUES = ("interactive", "automatic")


def _read_template(skill: str) -> str:
    return (TEMPLATES_DIR / skill / "SKILL.md").read_text(encoding="utf-8")


def _orchestrator_system_prompt() -> str:
    """The orchestrator persona's system_prompt — the TRUE source of the SDD
    orchestrator instruction. ``configurator.service._render_persona`` writes this
    verbatim into the installed ``.claude/agents/oc-orchestrator.md`` on install, so
    asserting the source keeps the contract stable regardless of install state."""
    from opencontext_core.personas import get_persona

    persona = get_persona("oc-orchestrator")
    assert persona is not None, "oc-orchestrator persona must exist"
    return persona.system_prompt


def _oc_new_command_body() -> str:
    """The ``oc-new`` slash-command body — the TRUE source of the installed
    ``.claude/commands/oc-new.md`` (rendered verbatim by ``service._plan_commands``)."""
    from opencontext_core.configurator import constants

    for name, _desc, body in constants.OPENCONTEXT_COMMANDS:
        if name == "oc-new":
            return body
    raise AssertionError("oc-new command must exist in OPENCONTEXT_COMMANDS")


# --------------------------------------------------------------------------- #
# Behaviour 2 — proposal question round in the oc-propose skill (shipped source)
# --------------------------------------------------------------------------- #


class TestProposalQuestionRound:
    """``oc-propose`` shapes the proposal with predefined-option product questions."""

    def test_names_a_proposal_question_round(self) -> None:
        content = _read_template("oc-propose").lower()
        assert "proposal question round" in content, (
            "oc-propose must run a proposal question round before writing the proposal"
        )

    def test_asks_before_writing_the_proposal(self) -> None:
        content = _read_template("oc-propose").lower()
        # The round must be positioned BEFORE the proposal is written.
        assert "before writing" in content or "before you write" in content, (
            "oc-propose must ask the questions BEFORE writing the proposal"
        )

    def test_asks_three_to_five_questions(self) -> None:
        content = _read_template("oc-propose")
        # The template may use an en-dash or a plain hyphen; the en-dash literal is
        # intentional so the assertion matches the artifact byte-for-byte.
        assert "3–5" in content or "3-5" in content, (  # noqa: RUF001 - en-dash matches template
            "oc-propose must ask 3 to 5 concrete product questions per round"
        )

    def test_questions_are_predefined_option(self) -> None:
        content = _read_template("oc-propose").lower()
        assert "predefined-option" in content, (
            "oc-propose questions must be predefined-option (not free-text)"
        )

    def test_only_free_text_is_the_task_idea(self) -> None:
        content = _read_template("oc-propose").lower()
        # The task/idea string is the sole free-text input; everything else selects.
        assert "sole free-text" in content or "only free-text" in content, (
            "oc-propose must state the task/idea is the only free-text input"
        )

    def test_covers_core_product_dimensions(self) -> None:
        content = _read_template("oc-propose").lower()
        for dimension in (
            "business problem",
            "target users",
            "business rules",
            "product outcome",
            "edge cases",
        ):
            assert dimension in content, f"oc-propose question round must cover '{dimension}'"

    def test_summarizes_and_offers_accept_revise_second_round(self) -> None:
        content = _read_template("oc-propose").lower()
        assert "summarize" in content or "summarise" in content, (
            "oc-propose must summarize the resulting assumptions"
        )
        for option in ("accept", "revise", "second round"):
            assert option in content, (
                f"oc-propose must offer '{option}' after summarizing assumptions"
            )

    def test_does_not_ask_harness_mechanics_at_proposal_time(self) -> None:
        content = _read_template("oc-propose").lower()
        # It must explicitly steer AWAY from delivery/harness questions here.
        assert "do not ask" in content and (
            "test command" in content or "pr shape" in content or "changed-line" in content
        ), "oc-propose must NOT ask harness mechanics (test commands, PR shape, budget)"

    def test_non_interactive_fallback_writes_a_section_and_never_hangs(self) -> None:
        content = _read_template("oc-propose")
        lower = content.lower()
        assert "## Proposal question round" in content, (
            "the non-interactive fallback must write a `## Proposal question round` section"
        )
        assert "not hang" in lower or "never hang" in lower or "do not hang" in lower, (
            "oc-propose must promise not to hang on a non-interactive/blocked host"
        )

    def test_artifact_stays_neutral_english(self) -> None:
        content = _read_template("oc-propose").lower()
        assert "neutral" in content and "english" in content, (
            "the proposal artifact must stay neutral English even if the Q&A is localized"
        )


# --------------------------------------------------------------------------- #
# Behaviour 1 — session preflight in the oc-new orchestrator entry point
# --------------------------------------------------------------------------- #


class TestSessionPreflight:
    """``oc-new`` reads session_choices or asks the four guided groups."""

    def test_names_a_session_preflight(self) -> None:
        content = _read_template("oc-new").lower()
        assert "session preflight" in content, "oc-new must run a session preflight first"

    def test_reads_session_choices_from_the_handoff(self) -> None:
        content = _read_template("oc-new")
        assert "session_choices" in content, (
            "oc-new must READ the handoff's session_choices when the CLI preflight ran"
        )
        assert "Honor the session choices" in content, (
            "oc-new must recognise the slice-1 'Honor the session choices' instruction line"
        )

    def test_asks_all_four_groups_when_no_session_choices(self) -> None:
        content = _read_template("oc-new").lower()
        for group in ("execution mode", "artifact store", "delivery", "chain"):
            assert group in content, f"session preflight must ask the '{group}' group"

    def test_uses_the_canonical_slice1_values(self) -> None:
        content = _read_template("oc-new")
        for value in ARTIFACT_STORE_VALUES:
            assert value in content, f"artifact store must offer canonical '{value}'"
        for value in DELIVERY_VALUES:
            assert value in content, f"delivery must offer canonical '{value}'"
        for value in CHAIN_VALUES:
            assert value in content, f"chain must offer canonical '{value}'"
        for value in EXECUTION_MODE_VALUES:
            assert value in content, f"execution mode must offer '{value}'"

    def test_questions_are_predefined_option_and_guided(self) -> None:
        content = _read_template("oc-new").lower()
        assert "predefined-option" in content, (
            "session preflight questions must be predefined-option"
        )
        # Guided = recommend + effect + safe default.
        assert "recommend" in content and "effect" in content and "safe default" in content, (
            "each preflight question must be guided (recommend + effect + safe default)"
        )

    def test_cached_for_session_not_reasked_per_phase(self) -> None:
        content = _read_template("oc-new").lower()
        assert "cache" in content and "do not re-ask" in content, (
            "preflight choices must be cached for the session, not re-asked per phase"
        )

    def test_non_interactive_fallback_uses_safe_defaults_and_never_hangs(self) -> None:
        content = _read_template("oc-new").lower()
        assert "non-interactive" in content or "ci" in content, (
            "oc-new must describe a non-interactive/CI fallback"
        )
        assert "not hang" in content or "never hang" in content or "do not hang" in content, (
            "the preflight fallback must promise not to hang"
        )


# --------------------------------------------------------------------------- #
# Behaviour 3 — interactive between-phase gate in the orchestrator
# --------------------------------------------------------------------------- #


class TestBetweenPhaseGate:
    """In interactive mode the orchestrator pauses and asks proceed/adjust/stop."""

    def test_names_the_between_phase_gate(self) -> None:
        content = _read_template("oc-new").lower()
        assert "between-phase" in content, "oc-new must define a between-phase gate"

    def test_only_in_interactive_mode(self) -> None:
        content = _read_template("oc-new").lower()
        assert "interactive" in content, "the between-phase gate applies in interactive mode"

    def test_pauses_summarizes_and_asks_proceed_adjust_stop(self) -> None:
        content = _read_template("oc-new").lower()
        assert "summarize" in content or "summarise" in content, (
            "the gate must summarize what the phase produced"
        )
        for option in ("proceed", "adjust", "stop"):
            assert option in content, f"the between-phase gate must offer '{option}'"

    def test_approval_is_phase_scoped(self) -> None:
        content = _read_template("oc-new").lower()
        assert "phase-scoped" in content, (
            "between-phase approval must be phase-scoped, not whole-pipeline"
        )


# --------------------------------------------------------------------------- #
# The same parity lives in the orchestrator persona SOURCE, which is rendered
# verbatim into the installed .claude/agents/oc-orchestrator.md on install.
# --------------------------------------------------------------------------- #


class TestOrchestratorPersonaCarriesParity:
    """The orchestrator persona's system_prompt carries the same contract.

    This is the shipped source (``personas/__init__.py``); the installed
    ``.claude/agents/oc-orchestrator.md`` is generated from it verbatim.
    """

    def test_orchestrator_has_session_preflight(self) -> None:
        content = _orchestrator_system_prompt()
        assert "session preflight" in content.lower()
        assert "session_choices" in content
        assert "Honor the session choices" in content

    def test_orchestrator_has_between_phase_gate(self) -> None:
        content = _orchestrator_system_prompt().lower()
        assert "between-phase" in content
        for option in ("proceed", "adjust", "stop"):
            assert option in content
        assert "phase-scoped" in content

    def test_orchestrator_uses_canonical_values(self) -> None:
        content = _orchestrator_system_prompt()
        for value in (*ARTIFACT_STORE_VALUES, *DELIVERY_VALUES, *CHAIN_VALUES):
            assert value in content, f"orchestrator persona must name canonical '{value}'"

    def test_installed_agent_file_is_generated_from_this_source(self) -> None:
        # The installed agent .md is rendered from the persona verbatim; assert the
        # generator wiring so the parity is guaranteed to reach the on-disk file.
        from opencontext_core.configurator.service import _render_persona
        from opencontext_core.personas import get_persona

        persona = get_persona("oc-orchestrator")
        assert persona is not None
        rendered = _render_persona(persona)
        assert "session preflight" in rendered.lower()
        assert "between-phase" in rendered.lower()


class TestOcNewCommandCarriesParity:
    """The ``oc-new`` slash-command body points at the preflight + question round.

    This is the shipped source (``configurator/constants.OPENCONTEXT_COMMANDS``); the
    installed ``.claude/commands/oc-new.md`` is generated from it verbatim.
    """

    def test_command_names_session_preflight_first(self) -> None:
        body = _oc_new_command_body().lower()
        assert "session preflight first" in body
        assert "session_choices" in _oc_new_command_body()

    def test_command_lists_the_four_guided_groups(self) -> None:
        body = _oc_new_command_body().lower()
        for group in ("execution mode", "artifact store", "delivery", "chain"):
            assert group in body

    def test_command_uses_canonical_values(self) -> None:
        body = _oc_new_command_body()
        for value in (*ARTIFACT_STORE_VALUES, *DELIVERY_VALUES, *CHAIN_VALUES):
            assert value in body, f"oc-new command must name canonical '{value}'"

    def test_command_points_at_proposal_question_round(self) -> None:
        body = _oc_new_command_body()
        assert "proposal question round" in body.lower()
        assert "accept/revise/second-round" in body

    def test_command_promises_non_interactive_fallback(self) -> None:
        body = _oc_new_command_body().lower()
        assert "never hangs" in body or "never hang" in body
