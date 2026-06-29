"""Known capability ids and the five built-in execution profiles (CP-008).

This registry is the single source of the capability id vocabulary that PR-003
(``WorkflowDefinition.required_capabilities``) and the Brain (PR-000.1) reference,
and of the five built-in ``ExecutionProfile``s. The profiles are declared as
*data*, not behaviour, so they stay inspectable and plugin-extensible.

The five execution profiles are intentionally distinct from the model profiles
(``sdd_model_profile``: default/cheap/hybrid/premium) and the setup presets
(``setup/presets.py``: full/enterprise/air-gapped/...). See
``profiles/definition.py`` for the model-profile-vs-execution-profile rationale.

Layering (doc 58): L3. Imports only the sibling L3 ``profiles.definition`` models.
"""

from __future__ import annotations

from opencontext_core.capabilities.detector import STRICT_HARNESS
from opencontext_core.profiles.definition import ExecutionProfile, HarnessStrictness

# Stable capability id vocabulary (the ids ``detect_test_capabilities`` emits plus
# the synthetic harness id). Provider/agent ids are namespaced at detection time
# (``provider.<name>`` / ``agent.<name>``) and are not enumerated here.
KNOWN_TOOLING_CAPABILITIES: tuple[str, ...] = (
    "pytest",
    "ruff-check",
    "mypy",
    "go-test",
    "cargo-test",
    STRICT_HARNESS,
)

# The five built-in execution profiles (CP-008). Each binds a distinct budget /
# retry / strictness / routing posture.
BUILTIN_PROFILES: dict[str, ExecutionProfile] = {
    "balanced": ExecutionProfile(
        id="balanced",
        token_budget=3000,
        max_retries=2,
        harness_strictness=HarnessStrictness.warn,
        provider_routing="policy",
        description="Default posture: moderate budget, warn-level harness, policy routing.",
    ),
    "low-cost": ExecutionProfile(
        id="low-cost",
        token_budget=1500,
        max_retries=1,
        harness_strictness=HarnessStrictness.advisory,
        provider_routing="local_first",
        description="Minimise spend: small budget, advisory harness, prefer local provider.",
    ),
    "enterprise": ExecutionProfile(
        id="enterprise",
        token_budget=4000,
        max_retries=3,
        harness_strictness=HarnessStrictness.strict,
        provider_routing="policy",
        description="Governed posture: blocking harness, policy-bound provider routing.",
    ),
    "research": ExecutionProfile(
        id="research",
        token_budget=6000,
        max_retries=3,
        harness_strictness=HarnessStrictness.warn,
        provider_routing="remote_first",
        description="Exploration: large budget, warn harness, strong remote models.",
    ),
    "performance": ExecutionProfile(
        id="performance",
        token_budget=8000,
        max_retries=2,
        harness_strictness=HarnessStrictness.warn,
        provider_routing="remote_first",
        description="Maximum capability: largest budget, remote-first routing.",
    ),
}

# The default profile a first run uses with no manual setup (CP, success criteria).
DEFAULT_PROFILE_ID = "balanced"


def builtin_profile_ids() -> list[str]:
    """Return the ids of the built-in execution profiles in declaration order."""
    return list(BUILTIN_PROFILES)


def get_profile(profile_id: str) -> ExecutionProfile | None:
    """Return the built-in profile for ``profile_id`` or ``None`` when unknown."""
    return BUILTIN_PROFILES.get(profile_id)
