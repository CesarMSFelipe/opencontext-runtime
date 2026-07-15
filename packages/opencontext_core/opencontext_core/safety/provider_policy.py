"""Provider policy enforcement."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from opencontext_core.config import ProviderPolicyConfig, SecurityConfig, SecurityMode
from opencontext_core.models.context import ContextItem, DataClassification


class ProviderPolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason: str


class ProviderPolicyEnforcer:
    def __init__(
        self,
        policies: list[ProviderPolicyConfig],
        security: SecurityConfig,
    ) -> None:
        self._by_provider = {policy.provider: policy for policy in policies}
        self._security = security

    def check(
        self,
        provider: str,
        items: list[ContextItem],
        provider_metadata: dict[str, bool] | None = None,
    ) -> ProviderPolicyDecision:
        metadata = provider_metadata or {}
        local_providers = {"mock", "local"}
        if self._security.mode is SecurityMode.AIR_GAPPED and provider not in local_providers:
            return ProviderPolicyDecision(
                allowed=False,
                reason="air_gapped_blocks_external_provider",
            )
        if not self._security.external_providers_enabled and provider not in local_providers:
            return ProviderPolicyDecision(allowed=False, reason="external_providers_disabled")
        policy = self._by_provider.get(provider)
        if policy is None:
            return ProviderPolicyDecision(allowed=False, reason="missing_provider_policy")
        if not policy.allowed:
            return ProviderPolicyDecision(allowed=False, reason="provider_disallowed")
        if provider not in local_providers and policy.require_redaction:
            for item in items:
                if item.metadata.get("redacted") is False:
                    return ProviderPolicyDecision(
                        allowed=False,
                        reason="provider_requires_redaction",
                    )
        if self._security.mode in {SecurityMode.ENTERPRISE, SecurityMode.AIR_GAPPED}:
            if policy.require_private_endpoint and provider not in local_providers:
                if not metadata.get("private_endpoint", False):
                    return ProviderPolicyDecision(
                        allowed=False,
                        reason="provider_requires_private_endpoint",
                    )
            if not policy.allow_training_opt_in and provider not in local_providers:
                if metadata.get("training_opt_in", False):
                    return ProviderPolicyDecision(
                        allowed=False,
                        reason="provider_training_opt_in_not_allowed",
                    )
            if policy.require_zero_data_retention and provider not in local_providers:
                if not metadata.get("zero_data_retention", False):
                    return ProviderPolicyDecision(
                        allowed=False,
                        reason="provider_requires_zero_data_retention",
                    )
        allowed = {DataClassification(value) for value in policy.allowed_classifications}
        for item in items:
            if item.classification not in allowed:
                return ProviderPolicyDecision(
                    allowed=False,
                    reason=f"classification_not_allowed:{item.classification.value}",
                )
        return ProviderPolicyDecision(allowed=True, reason="allowed")
