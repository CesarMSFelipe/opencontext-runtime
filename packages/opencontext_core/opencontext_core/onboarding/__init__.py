"""Onboarding service — unifies workspace, config, agents, SDD, and harness setup."""

from opencontext_core.onboarding.checklist import (
    ChecklistItem,
    DxChecklist,
    run_checklist,
)
from opencontext_core.onboarding.metrics import DxMetrics
from opencontext_core.onboarding.service import (
    OnboardingOptions,
    OnboardingResult,
    OnboardingService,
    default_active_clients,
)
from opencontext_core.onboarding.wizard import (
    InteractiveOnboardingWizard,
    OnboardingWizard,
    StackDetection,
    StepRecord,
    WizardReport,
    WizardStep,
    run_onboarding,
)

__all__ = [
    "ChecklistItem",
    "DxChecklist",
    "DxMetrics",
    "InteractiveOnboardingWizard",
    "OnboardingOptions",
    "OnboardingResult",
    "OnboardingService",
    "OnboardingWizard",
    "StackDetection",
    "StepRecord",
    "WizardReport",
    "WizardStep",
    "default_active_clients",
    "run_checklist",
    "run_onboarding",
]
