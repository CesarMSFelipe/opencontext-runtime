"""Central fail-closed checks before context crosses runtime boundaries."""

from __future__ import annotations

from collections.abc import Callable
from typing import NoReturn

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.config import OpenContextConfig
from opencontext_core.models.context import ContextItem, DataClassification
from opencontext_core.models.trace import RuntimeTrace
from opencontext_core.safety.prompt_injection import PromptInjectionScanner
from opencontext_core.safety.provider_policy import ProviderPolicyDecision, ProviderPolicyEnforcer
from opencontext_core.safety.secrets import SecretScanner


class FirewallDecision(BaseModel):
    """Traceable allow/block decision from the ContextFirewall."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool = Field(description="Whether the guarded operation may proceed.")
    reason: str = Field(description="Stable machine-readable reason.")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking safety warnings.")
    alternatives: list[str] = Field(
        default_factory=list,
        description="Safe follow-up options when the operation is blocked.",
    )

    def raise_if_blocked(self) -> None:
        """Raise a RuntimeError if the operation is blocked."""

        if self.allowed:
            return
        raise FirewallBlockedError(self.reason, self.alternatives)


class FirewallBlockedError(RuntimeError):
    """Raised when a runtime boundary is blocked by policy."""

    def __init__(self, reason: str, alternatives: list[str]) -> None:
        self.reason = reason
        self.alternatives = alternatives
        super().__init__(_format_block(reason, alternatives))


class ContextFirewall:
    """Central security gate for prompts, providers, traces, and exports."""

    def __init__(
        self,
        config: OpenContextConfig,
        *,
        on_secret_detected: Callable[[str, list[str]], None] | None = None,
    ) -> None:
        self._config = config
        self._secret_scanner = SecretScanner()
        self._injection_scanner = PromptInjectionScanner()
        # Optional ``secret.detected`` emission hook (EVENT-1 / task 4.2). Called
        # with ``(sink, secret_kinds)`` on a secret hit before the firewall blocks
        # or redacts. Default ``None`` keeps the firewall a pure enforcer.
        self._on_secret_detected = on_secret_detected

    def _emit_secret_detected(self, sink: str, text: str) -> None:
        if self._on_secret_detected is None:
            return
        kinds = sorted({f.kind for f in self._secret_scanner.scan(text)})
        if kinds:
            self._on_secret_detected(sink, kinds)

    def check_context_export(self, items: list[ContextItem], *, sink: str) -> FirewallDecision:
        """Block raw secret-bearing context before export-like sinks."""

        warnings = self._context_warnings(items)
        redacted_ids: list[str] = []
        for item in items:
            # Redact-and-continue: a benign secret-like fixture (a .env example, an
            # sk-… token in a test) must not hard-fail a local export (pack/context).
            # Sanitizing in place strips the raw value, so downstream sinks — including
            # the provider egress gate (check_provider_call) — still see clean content.
            if self._secret_scanner.scan(item.content):
                self._emit_secret_detected(sink, item.content)
                redacted = self._secret_scanner.redact(item.content)
                if self._secret_scanner.scan(redacted):
                    # Redaction could not fully sanitize — keep the hard block.
                    return _blocked(
                        "raw_secret_detected_before_context_export",
                        [
                            "Redact the context item before export.",
                            "Omit the source from the pack.",
                            "Keep the operation local and sanitized.",
                        ],
                        warnings,
                    )
                item.content = redacted
                item.redacted = True
                item.metadata["redacted"] = True
                redacted_ids.append(item.id)
            if item.classification in {DataClassification.SECRET, DataClassification.REGULATED}:
                if not item.redacted and item.metadata.get("redacted") is not True:
                    return _blocked(
                        f"{item.classification.value}_context_requires_redaction",
                        [
                            "Redact high-risk context before export.",
                            "Use a local-only provider or repo-map-only context.",
                        ],
                        warnings,
                    )
        if redacted_ids:
            warnings.append(f"redacted_secrets={len(redacted_ids)}")
        return FirewallDecision(
            allowed=True,
            reason=f"{sink}_allowed",
            warnings=warnings,
        )

    def check_provider_call(
        self,
        provider: str,
        items: list[ContextItem],
        *,
        provider_metadata: dict[str, bool] | None = None,
    ) -> ProviderPolicyDecision:
        """Run secret checks and provider policy before every LLM call."""

        for item in items:
            if self._secret_scanner.scan(item.content):
                self._emit_secret_detected(f"provider:{provider}", item.content)
                return ProviderPolicyDecision(
                    allowed=False,
                    reason="raw_secret_detected_before_provider_call",
                )
        return ProviderPolicyEnforcer(
            self._config.provider_policies,
            self._config.security,
        ).check(provider, items, provider_metadata=provider_metadata)

    def check_trace_persistence(self, trace: RuntimeTrace) -> FirewallDecision:
        """Block traces that still contain raw secret-like values."""

        serialized = trace.model_dump_json()
        if self._secret_scanner.scan(serialized):
            return _blocked(
                "raw_secret_detected_before_trace_persistence",
                [
                    "Sanitize the trace before persistence.",
                    "Persist fingerprints and token counts instead of raw content.",
                ],
            )
        return FirewallDecision(allowed=True, reason="trace_persistence_allowed")

    def _context_warnings(self, items: list[ContextItem]) -> list[str]:
        warnings: list[str] = []
        for item in items:
            injection_findings = self._injection_scanner.scan(item.content)
            if injection_findings:
                warnings.append(f"{item.id}:prompt_injection_patterns={len(injection_findings)}")
        return warnings


def _blocked(
    reason: str,
    alternatives: list[str],
    warnings: list[str] | None = None,
) -> FirewallDecision:
    return FirewallDecision(
        allowed=False,
        reason=reason,
        warnings=warnings or [],
        alternatives=alternatives,
    )


def _format_block(reason: str, alternatives: list[str]) -> str:
    if not alternatives:
        return f"Blocked by ContextFirewall: {reason}"
    return "\n".join(
        [
            f"Blocked by ContextFirewall: {reason}",
            "Safe alternatives:",
            *[f"- {alternative}" for alternative in alternatives],
        ]
    )


def assert_never(value: NoReturn) -> NoReturn:
    """Typing helper for future exhaustive firewall dispatch."""

    raise AssertionError(f"Unhandled firewall value: {value}")
