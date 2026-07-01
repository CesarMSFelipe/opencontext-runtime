"""Deployment-mode primitives (PR-R2-A / `operations-deployment-modes`).

Implements REQ-ops-deploy-001 from the spec:
- ``DeployMode`` enum with the 5 named modes (LOCAL / CI_RUNNER / SHARED_REMOTE /
  HYBRID_EDGE_CLOUD / AIR_GAPPED).
- ``DeployConfig`` frozen dataclass that binds a mode with its settings
  (``remote_url``, ``telemetry_opt_in``).
- ``detect_deploy_mode()`` reads ``OPENCONTEXT_DEPLOY_MODE`` from the env, with a
  LOCAL default and a few CLI-friendly aliases.

Layer: L11 (interfaces). No upward imports. Pure stdlib, no I/O.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum


# ponytail: spec REQ-ops-deploy-001 names the 5 modes by these exact identifiers.
# Values stay lowercase (CLI / env var friendly) — we only ever compare by .value.
class DeployMode(StrEnum):
    LOCAL = "local"
    CI_RUNNER = "ci_runner"
    SHARED_REMOTE = "shared_remote"
    HYBRID_EDGE_CLOUD = "hybrid_edge_cloud"
    AIR_GAPPED = "air_gapped"


# CLI / docs may use these spellings; we normalise to the canonical enum.
_ALIASES: dict[str, DeployMode] = {
    "local": DeployMode.LOCAL,
    "ci": DeployMode.CI_RUNNER,
    "ci-runner": DeployMode.CI_RUNNER,
    "ci_runner": DeployMode.CI_RUNNER,
    "remote": DeployMode.SHARED_REMOTE,
    "shared-remote": DeployMode.SHARED_REMOTE,
    "shared_remote": DeployMode.SHARED_REMOTE,
    "hybrid": DeployMode.HYBRID_EDGE_CLOUD,
    "hybrid-edge-cloud": DeployMode.HYBRID_EDGE_CLOUD,
    "hybrid_edge_cloud": DeployMode.HYBRID_EDGE_CLOUD,
    "air-gapped": DeployMode.AIR_GAPPED,
    "air_gapped": DeployMode.AIR_GAPPED,
    "airgapped": DeployMode.AIR_GAPPED,
}

_ENV_VAR = "OPENCONTEXT_DEPLOY_MODE"


@dataclass(frozen=True)
class DeployConfig:
    """Immutable deploy settings for one session.

    AIR_GAPPED is the only inviolable mode: ``telemetry_opt_in`` is forced to
    ``False`` in ``__post_init__`` no matter what the caller passes.
    """

    mode: DeployMode
    remote_url: str | None = None
    telemetry_opt_in: bool = False
    # ponytail: extra passthrough for future fields (e.g. backup target).
    # frozen=True + field(default_factory=...) is the standard recipe.
    extras: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Spec: "AIR_GAPPED mode SHALL refuse any opt_in=True override".
        if self.mode is DeployMode.AIR_GAPPED and self.telemetry_opt_in is True:
            # frozen=True forbids setattr, so we go through object.__setattr__.
            object.__setattr__(self, "telemetry_opt_in", False)


def detect_deploy_mode(env: dict[str, str] | None = None) -> DeployMode:
    """Return the deploy mode from ``OPENCONTEXT_DEPLOY_MODE``, defaulting to LOCAL.

    Accepts both canonical names (``ci_runner``) and CLI-friendly spellings
    (``ci``, ``air-gapped``). Empty / missing env → LOCAL.
    """
    raw = (env or os.environ).get(_ENV_VAR, "").strip().lower()
    if not raw:
        return DeployMode.LOCAL
    if raw not in _ALIASES:
        # Spec doesn't require a specific error class — ValueError is the
        # Pythonic contract for "value not in allowed set".
        raise ValueError(
            f"unknown {_ENV_VAR}={raw!r}; expected one of: "
            + ", ".join(sorted({m.value for m in DeployMode}))
        )
    return _ALIASES[raw]
