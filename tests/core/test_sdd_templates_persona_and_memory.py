"""SDD phase skill templates must RUN AS their persona and carry the memory loop.

Workstream STEP 3/4 of ``oc-memory-parity-and-polish``.

The SDD phase templates (``skills/templates/oc-*/SKILL.md``) are static markdown
shipped verbatim to ``.opencontext/skills/``. Two gaps are closed here:

* **STEP 3 — run AS the persona.** Each phase must SPAWN its mapped persona
  subagent (Claude Code ``Task`` tool with ``subagent_type: oc-<persona>``) and
  delegate the phase to it — not merely narrate "Adopt the … persona". The
  ``PHASE_PERSONAS`` map in ``personas.py`` is the single source of truth; the
  templates name exactly that persona, and these tests read the map rather than
  hard-coding it.
* **STEP 4 — the multi-level memory loop.** Each phase must PRIME at start
  (``opencontext_memory_context``) and SAVE at end (``opencontext_memory_save``),
  both scoped to *this* change via the documented ``change:<slug>`` key/tags
  convention, with an explicit memory layer.

Templates are markdown, so the assertions are on file content.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.personas import PHASE_PERSONAS, get_persona

TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "opencontext_core"
    / "opencontext_core"
    / "skills"
    / "templates"
)

# The SDD phase skills the developer drives, mapped to the *phase key* used in
# ``PHASE_PERSONAS``. ``archive`` has no entry in the map (it is not a harness
# driver phase); it persists the cycle, so it runs as the Orchestrator.
PHASE_SKILL_TO_PHASE: dict[str, str] = {
    "oc-explore": "explore",
    "oc-propose": "propose",
    "oc-spec": "spec",
    "oc-design": "design",
    "oc-tasks": "tasks",
    "oc-apply": "apply",
    "oc-verify": "verify",
}

# Phase skills whose driving persona is not a ``PHASE_PERSONAS`` key.
EXTRA_SKILL_PERSONA: dict[str, str] = {
    "oc-archive": "oc-orchestrator",
}

# Every phase skill (the per-phase ones plus the all-in-one entry point).
ALL_PHASE_SKILLS: tuple[str, ...] = (
    *PHASE_SKILL_TO_PHASE,
    *EXTRA_SKILL_PERSONA,
)

# Valid memory layers exposed by ``opencontext_memory_save`` (see mcp_stdio).
MEMORY_LAYERS: tuple[str, ...] = (
    "EPISODIC",
    "SEMANTIC",
    "PROCEDURAL",
    "WORKING",
    "FAILURE",
)


def _persona_for_skill(skill: str) -> str:
    """The persona id a phase skill must run as (single source of truth)."""

    if skill in PHASE_SKILL_TO_PHASE:
        return PHASE_PERSONAS[PHASE_SKILL_TO_PHASE[skill]]
    return EXTRA_SKILL_PERSONA[skill]


def _read(skill: str) -> str:
    return (TEMPLATES_DIR / skill / "SKILL.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# STEP 3 — each phase actually RUNS AS its mapped persona subagent.
# --------------------------------------------------------------------------- #


class TestPhaseSpawnsPersonaSubagent:
    """Phase templates spawn the mapped persona subagent, not narrate it."""

    def test_every_phase_spawns_its_mapped_persona_subagent(self) -> None:
        for skill in ALL_PHASE_SKILLS:
            persona = _persona_for_skill(skill)
            # The persona id must be a real persona (catches typos / drift).
            assert get_persona(persona) is not None, f"{skill}: '{persona}' is not a known persona"
            content = _read(skill)
            assert f"subagent_type: {persona}" in content, (
                f"{skill}: must SPAWN the '{persona}' subagent via "
                f"`subagent_type: {persona}` (Task tool), not narrate the persona"
            )

    def test_every_phase_uses_the_task_tool_to_spawn(self) -> None:
        for skill in ALL_PHASE_SKILLS:
            content = _read(skill)
            assert "Task tool" in content, (
                f"{skill}: the persona must be spawned via the Claude Code Task tool"
            )

    def test_phases_do_not_merely_narrate_adopt_the_persona(self) -> None:
        # The old "Adopt the **OC …** persona" narration is the bug being fixed.
        for skill in PHASE_SKILL_TO_PHASE:
            content = _read(skill)
            assert "Adopt the" not in content, (
                f"{skill}: still narrates 'Adopt the … persona' instead of spawning it"
            )

    def test_mapping_is_not_duplicated_as_a_literal_table(self) -> None:
        # Guard against re-introducing a hand-maintained phase→persona table that
        # would drift from PHASE_PERSONAS. Each template names only the persona(s)
        # it is allowed to spawn. ``oc-apply`` is the one phase that, by design,
        # also spawns ``oc-tester`` (PHASE_PERSONAS["test"]) for the failing tests
        # under strict TDD — so that pairing is allowed there.
        allowed_extra: dict[str, set[str]] = {
            "oc-apply": {PHASE_PERSONAS["test"]},
        }
        for skill in PHASE_SKILL_TO_PHASE:
            persona = _persona_for_skill(skill)
            content = _read(skill)
            permitted = {persona} | allowed_extra.get(skill, set())
            stray = (set(PHASE_PERSONAS.values()) | set(EXTRA_SKILL_PERSONA.values())) - permitted
            for other in stray:
                assert f"subagent_type: {other}" not in content, (
                    f"{skill}: spawns an unexpected persona '{other}'"
                )


# --------------------------------------------------------------------------- #
# STEP 4 — the multi-level memory loop is wired into every phase.
# --------------------------------------------------------------------------- #


class TestPhaseMemoryLoop:
    """Each phase primes from prior memory and saves its own, change-scoped."""

    def test_every_phase_primes_from_change_memory_at_start(self) -> None:
        for skill in ALL_PHASE_SKILLS:
            content = _read(skill)
            assert "opencontext_memory_context" in content, (
                f"{skill}: must PRIME at start via `opencontext_memory_context`"
            )

    def test_every_phase_saves_its_findings_at_end(self) -> None:
        for skill in ALL_PHASE_SKILLS:
            content = _read(skill)
            assert "opencontext_memory_save" in content, (
                f"{skill}: must SAVE at end via `opencontext_memory_save`"
            )

    def test_memory_is_scoped_to_this_change(self) -> None:
        # The documented per-change scope convention: key/tags = ``change:<slug>``.
        for skill in ALL_PHASE_SKILLS:
            content = _read(skill)
            assert "change:<slug>" in content, (
                f"{skill}: memory must be namespaced to the change via the "
                f"`change:<slug>` key/tags convention"
            )

    def test_save_names_an_explicit_memory_layer(self) -> None:
        for skill in ALL_PHASE_SKILLS:
            content = _read(skill)
            assert any(layer in content for layer in MEMORY_LAYERS), (
                f"{skill}: the SAVE step must name a memory layer "
                f"(one of {', '.join(MEMORY_LAYERS)})"
            )


# --------------------------------------------------------------------------- #
# The oc-new all-in-one template drives the per-phase persona spawns.
# --------------------------------------------------------------------------- #


class TestOcNewDrivesPerPhaseSpawns:
    """``oc-new`` runs the whole flow by spawning each phase's persona in turn."""

    def test_oc_new_spawns_every_phase_persona(self) -> None:
        content = _read("oc-new")
        for persona in (
            "oc-explorer",
            "oc-orchestrator",
            "oc-architect",
            "oc-builder",
            "oc-reviewer",
        ):
            assert f"subagent_type: {persona}" in content, (
                f"oc-new must drive the flow by spawning the '{persona}' subagent"
            )

    def test_oc_new_carries_the_memory_loop(self) -> None:
        content = _read("oc-new")
        assert "opencontext_memory_context" in content
        assert "opencontext_memory_save" in content
        assert "change:<slug>" in content
