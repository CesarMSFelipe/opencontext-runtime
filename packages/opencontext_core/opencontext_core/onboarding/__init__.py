"""Onboarding service — unifies workspace, config, agents, SDD, and harness setup."""

from opencontext_core.onboarding.service import (
    OnboardingOptions,
    OnboardingResult,
    OnboardingService,
    default_active_clients,
)

__all__ = [
    "OnboardingOptions",
    "OnboardingResult",
    "OnboardingService",
    "default_active_clients",
]
