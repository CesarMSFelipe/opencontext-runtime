"""Telemetry opt-in matrix per mode (REQ-ops-deploy-004).

``TelemetryOptIn`` is a small frozen dataclass: ``opt_in``, ``sample_rate``,
``redact_keys``. The matrix is computed by ``telemetry_policy_for(mode)`` —
callers should use it instead of constructing a policy by hand so that the
AIR_GAPPED override is centralised here.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field

from opencontext_core.operations.deploy import DeployConfig, DeployMode

# NOTE: spec REQ-ops-deploy-004 lists the exact redaction key set.
# Defense-in-depth: even when opt_in=True, these keys are redacted at the
# sender. The glob patterns ("*_TOKEN", "*_SECRET") are matched by the
# sender, not by this module.
DEFAULT_REDACT_KEYS: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "*_TOKEN",
        "*_SECRET",
    }
)

# Per-mode defaults from the spec. AIR_GAPPED is always off (and enforced
# again in telemetry_policy_for). CI defaults to off per spec scenario
# "Mode round-trips from CLI flag".
_MODE_DEFAULT_OPT_IN: dict[DeployMode, bool] = {
    DeployMode.LOCAL: True,
    DeployMode.CI_RUNNER: False,
    DeployMode.SHARED_REMOTE: True,
    DeployMode.HYBRID_EDGE_CLOUD: True,
    DeployMode.AIR_GAPPED: False,
}


@dataclass(frozen=True)
class TelemetryOptIn:
    """The per-mode telemetry contract.

    ``redact_keys`` is a set of literal keys + glob patterns. The sender
    matches each env / log key against the set; a hit ⇒ value is replaced
    with ``[REDACTED]`` before any upload.
    """

    opt_in: bool
    sample_rate: float = 0.0
    redact_keys: frozenset[str] = field(default_factory=lambda: DEFAULT_REDACT_KEYS)

    def __post_init__(self) -> None:
        # sample_rate is a probability
        if not 0.0 <= self.sample_rate <= 1.0:
            raise ValueError(f"sample_rate must be in [0, 1], got {self.sample_rate!r}")


def telemetry_policy_for(
    mode: DeployMode,
    *,
    config: DeployConfig | None = None,
    env: dict[str, str] | None = None,
    redact_keys: Iterable[str] | None = None,
) -> TelemetryOptIn:
    """Return the per-mode telemetry policy.

    Resolution order for ``opt_in``:
    1. If ``mode is AIR_GAPPED`` → always False (inviolable).
    2. Else if ``OPENCONTEXT_TELEMETRY=1`` in env → True.
    3. Else the per-mode default.
    4. If a ``DeployConfig`` is supplied AND its ``telemetry_opt_in`` differs
       from the default, that wins (caller override). Still subject to rule 1.
    """
    base_opt_in = _MODE_DEFAULT_OPT_IN[mode]

    env_map = env if env is not None else os.environ
    if env_map.get("OPENCONTEXT_TELEMETRY") == "1":
        base_opt_in = True

    if config is not None and config.telemetry_opt_in is not base_opt_in:
        base_opt_in = config.telemetry_opt_in

    # Rule 1: AIR_GAPPED is inviolable. (DeployConfig also forces this in
    # __post_init__, but we re-check here in case the caller constructed
    # the policy by hand.)
    if mode is DeployMode.AIR_GAPPED:
        base_opt_in = False

    keys = frozenset(redact_keys) if redact_keys is not None else DEFAULT_REDACT_KEYS

    return TelemetryOptIn(opt_in=base_opt_in, sample_rate=1.0, redact_keys=keys)
