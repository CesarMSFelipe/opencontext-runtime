"""PersonaHandoff — explicit persona-to-persona handoff view (PR-006, book §11).

The runtime already carries an explicit, serializable handoff (``AgentHandoff``,
``oc_new/models.py`` schema v2) that exceeds the book's ``PersonaHandoff`` — it holds
``artifact_refs``/``expected_outputs``/``allowed_tools``/``denied_tools``. Rather than
introduce a second handoff model (the dual-model smell PR-001/003 removed), this
module is a thin *view-adapter* exposing the book's field names
(``from_persona``/``to_persona``/``constraints``/``open_questions``/
``next_expected_output``) mapped onto ``AgentHandoff``.

No persona depends on raw conversation history — only on this explicit object
(book §11, invariant 7).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.oc_new.models import AgentHandoff


class PersonaHandoff(BaseModel):
    """Book-shaped view over :class:`AgentHandoff` (doc 05 §11)."""

    model_config = ConfigDict(extra="forbid")

    from_persona: str = ""
    to_persona: str
    artifact_refs: list[str] = Field(default_factory=list)
    summary: str = ""
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    next_expected_output: str = ""

    @classmethod
    def from_agent_handoff(cls, handoff: AgentHandoff, *, from_persona: str = "") -> PersonaHandoff:
        """Project an :class:`AgentHandoff` onto the book's ``PersonaHandoff`` view.

        ``constraints`` are surfaced from the handoff's ``denied_tools`` (tool grants
        are the runtime-enforced constraints); ``open_questions``/``next_expected_output``
        are derived from ``required_inputs``/``expected_outputs``.
        """
        return cls(
            from_persona=from_persona,
            to_persona=handoff.persona,
            artifact_refs=[ref.path for ref in handoff.artifact_refs if ref.path],
            summary=handoff.previous_phase_summary or handoff.context_summary,
            constraints=[f"deny:{tool}" for tool in handoff.denied_tools],
            open_questions=list(handoff.required_inputs),
            next_expected_output=handoff.expected_outputs[0] if handoff.expected_outputs else "",
        )
