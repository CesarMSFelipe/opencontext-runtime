"""PersonaDefinition — first-class persona contract (PR-006, Persona Contract v1).

The book (doc 05 §5) promotes a persona from a prompt-string to a governed
engineering responsibility: responsibility, tools, required skills, output
contracts, token budget, escalation, and forbidden behaviours. The legacy
``Persona`` dataclass (``personas/__init__.py``) remains the single source of the
``system_prompt``/``tools``/``visibility``; this model is the envelope around it
plus the governance metadata, lifted via :meth:`PersonaDefinition.from_legacy`.

REG-CONV adds three typed sub-models so a persona is a *responsibility with a
decision strategy*, not a prompt style: ``PersonaStrategy`` (how it decides/
escalates), ``PersonaCapabilities`` (what it may use — enforced by Policy), and
``PersonaConstraints`` (what it may not do — enforced by Policy).

Layer L6: imports L0 (compat) + L6 base; the Policy Engine (L3) is reached lazily
in :meth:`tool_policy` (downward dependency, allowed by doc 58).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.registries.base import RegistryMetadata

if TYPE_CHECKING:  # avoid an import cycle: __init__ imports this module
    from opencontext_core.personas import Persona
    from opencontext_core.tools.policy import ToolPermissionPolicy

# Persona Contract v1 (doc 59 — internal contract versioning). Bumped on a breaking
# change to the persona schema; asserted by a guard test.
PERSONA_CONTRACT_VERSION = 1
PERSONA_SCHEMA_VERSION = "opencontext.persona.v1"


def persona_uid(slug: str) -> str:
    """Return the addressable global persona id ``persona_<slug>`` (doc 59 scheme)."""
    return f"persona_{slug}"


class PersonaStrategy(BaseModel):
    """How a persona decides, retries, diagnoses, and escalates (REG-CONV).

    Independent of any prompt wording — the strategy is what the runtime reads to
    govern the persona, so a persona is a responsibility with a decision strategy.
    """

    model_config = ConfigDict(extra="forbid")

    escalation_rules: list[str] = Field(default_factory=list)
    retry_policy: str = Field(
        default="bounded", description="How retries are handled: bounded | none | diagnosis."
    )
    diagnosis_policy: str = Field(
        default="none", description="Failure-diagnosis approach, e.g. 'three_hypotheses'."
    )
    max_attempts: int = Field(default=1, description="Attempt budget before escalation.")
    enforce_output_contract: bool = Field(
        default=True, description="Output is validated against the contract, not trusted as prose."
    )


class PersonaCapabilities(BaseModel):
    """Typed capability set a persona may use (REG-CONV), resolved by the runtime
    and enforced by the Policy Engine. Not a flat tool list — declares skills,
    harnesses, and provider tier too."""

    model_config = ConfigDict(extra="forbid")

    allowed_tools: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    optional_skills: list[str] = Field(default_factory=list)
    required_harnesses: list[str] = Field(default_factory=list)
    provider_tier: str = Field(
        default="standard", description="Provider routing tier the persona may use."
    )


class PersonaConstraints(BaseModel):
    """What a persona may NOT do (REG-CONV), enforced by Policy — not by prompt text."""

    model_config = ConfigDict(extra="forbid")

    disallowed_tools: list[str] = Field(default_factory=list)
    forbidden_behaviours: list[str] = Field(default_factory=list)
    token_budget: int = Field(default=0, description="0 = unbounded / inherit phase budget.")


class PersonaDefinition(BaseModel):
    """A registry-driven persona contract (book doc 05 §5 + REG-CONV)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=PERSONA_SCHEMA_VERSION)
    id: str = Field(description="Persona id (slug), e.g. 'oc-builder'. Registry key.")
    name: str = ""
    description: str = ""
    responsibility: str = Field(
        default="", description="The single engineering responsibility this role owns."
    )
    visibility: str = Field(
        default="hidden",
        description="public_main | public_support | hidden_delegation (legacy values preserved).",
    )
    default_tools: list[str] = Field(default_factory=list)
    disallowed_tools: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    optional_skills: list[str] = Field(default_factory=list)
    compatible_workflows: list[str] = Field(default_factory=list)
    compatible_nodes: list[str] = Field(default_factory=list)
    output_contracts: list[str] = Field(default_factory=list)
    token_budget: int = 0
    escalation_rules: list[str] = Field(default_factory=list)
    forbidden_behaviours: list[str] = Field(default_factory=list)
    system_prompt: str = ""

    # --- REG-CONV typed sub-models -----------------------------------------
    strategy: PersonaStrategy = Field(default_factory=PersonaStrategy)
    capabilities: PersonaCapabilities = Field(default_factory=PersonaCapabilities)
    constraints: PersonaConstraints = Field(default_factory=PersonaConstraints)

    # --- plugin-ready provenance (REG-CONV) --------------------------------
    metadata: RegistryMetadata = Field(default_factory=RegistryMetadata)

    @property
    def uid(self) -> str:
        """Addressable global persona id (doc 59 scheme)."""
        return persona_uid(self.id)

    @classmethod
    def from_legacy(cls, persona: Persona, **enrichment: Any) -> PersonaDefinition:
        """Build a definition from a legacy ``Persona`` plus governance enrichment.

        The dataclass supplies the prompt/tools/visibility; ``enrichment`` (typically
        the persona's ``builtins`` YAML entry) supplies responsibility, skills,
        harnesses, output contracts, escalation, and forbidden behaviours. The three
        REG-CONV sub-models are derived from those fields so they stay consistent.
        """
        default_tools = list(persona.tools)
        required_skills = list(enrichment.get("required_skills", []) or [])
        optional_skills = list(enrichment.get("optional_skills", []) or [])
        required_harnesses = list(enrichment.get("required_harnesses", []) or [])
        disallowed_tools = list(enrichment.get("disallowed_tools", []) or [])
        forbidden = list(enrichment.get("forbidden_behaviours", []) or [])
        escalation = list(enrichment.get("escalation_rules", []) or [])
        token_budget = int(enrichment.get("token_budget", 0) or 0)
        provider_tier = str(enrichment.get("provider_tier", "standard") or "standard")

        strategy = PersonaStrategy(
            escalation_rules=escalation,
            retry_policy=str(enrichment.get("retry_policy", "bounded") or "bounded"),
            diagnosis_policy=str(enrichment.get("diagnosis_policy", "none") or "none"),
            max_attempts=int(enrichment.get("max_attempts", 1) or 1),
            enforce_output_contract=bool(enrichment.get("enforce_output_contract", True)),
        )
        capabilities = PersonaCapabilities(
            allowed_tools=default_tools,
            required_skills=required_skills,
            optional_skills=optional_skills,
            required_harnesses=required_harnesses,
            provider_tier=provider_tier,
        )
        constraints = PersonaConstraints(
            disallowed_tools=disallowed_tools,
            forbidden_behaviours=forbidden,
            token_budget=token_budget,
        )
        return cls(
            id=persona.id,
            name=persona.name,
            description=persona.description,
            responsibility=str(enrichment.get("responsibility", "") or ""),
            visibility=str(persona.visibility),
            default_tools=default_tools,
            disallowed_tools=disallowed_tools,
            required_skills=required_skills,
            optional_skills=optional_skills,
            compatible_workflows=list(enrichment.get("compatible_workflows", []) or []),
            compatible_nodes=list(enrichment.get("compatible_nodes", []) or []),
            output_contracts=list(enrichment.get("output_contracts", []) or []),
            token_budget=token_budget,
            escalation_rules=escalation,
            forbidden_behaviours=forbidden,
            system_prompt=persona.system_prompt,
            strategy=strategy,
            capabilities=capabilities,
            constraints=constraints,
        )

    def to_legacy(self) -> Persona:
        """Project back onto the legacy ``Persona`` dataclass (backward-compat)."""
        from opencontext_core.personas import Persona, PersonaVisibility

        try:
            vis = PersonaVisibility(self.visibility)
        except ValueError:
            vis = PersonaVisibility.HIDDEN_DELEGATION
        return Persona(
            id=self.id,
            name=self.name,
            description=self.description,
            system_prompt=self.system_prompt,
            tools=tuple(self.default_tools),
            visibility=vis,
        )

    def tool_policy(self, *, security_mode: Any = None, mode: Any = None) -> ToolPermissionPolicy:
        """Build a ``ToolPermissionPolicy`` enforcing this persona's tool grants.

        ``allowed_tools`` = ``default_tools``; ``denied_tools`` = ``disallowed_tools``
        (constraints win — denied first). Enforcement is runtime, not prompt text
        (book §9; REG-CONV PersonaConstraints). Policy is L3, imported lazily.
        """
        from opencontext_core.tools.policy import ToolExecutionMode, ToolPermissionPolicy

        kwargs: dict[str, Any] = {
            "allowed_tools": set(self.default_tools),
            "denied_tools": set(self.constraints.disallowed_tools),
        }
        if security_mode is not None:
            kwargs["security_mode"] = security_mode
        kwargs["mode"] = mode if mode is not None else ToolExecutionMode.DEFAULT
        return ToolPermissionPolicy(**kwargs)
