"""Unified Policy Engine (SPEC PE-1).

``PolicyEngine.evaluate(operation)`` is the single runtime seam through which
every governed mutating or external operation passes (file, command, network,
provider, secret, memory, plugin, auto-apply, cache, kg_write). It dispatches to
the *existing, already-wired* enforcers and normalizes their heterogeneous
outputs into one canonical :class:`PolicyDecision` — the engine adds no new
denials on the MET surfaces (parity is the design contract); the genuinely new
enforcement is the command branch (classifier + forbidden-command deny-list),
the auto-apply tiers, the memory forbidden-content rule, the cache/KG governance
branches, and the CI fail-closed downgrade.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.actions.policy import ActionRequest, ActionType, evaluate_action
from opencontext_core.config import SecurityMode
from opencontext_core.policy.auto_apply import AutoApplyPolicy
from opencontext_core.policy.commands import CommandCategory, CommandClassifier
from opencontext_core.policy.events import emit_policy_events
from opencontext_core.policy.memory_content import forbidden_memory_content
from opencontext_core.policy.models import (
    POLICY_CONTRACT_VERSION,
    PolicyDecision,
)
from opencontext_core.policy.presets import (
    PolicyPreset,
    PresetPosture,
    exceeds_ceiling,
    posture_for,
    preset_from_security_mode,
    resolve_preset,
    security_mode_for_preset,
)
from opencontext_core.safety.secrets import SecretScanner

if TYPE_CHECKING:
    from opencontext_core.config import OpenContextConfig
    from opencontext_core.models.run_envelope import RunEnvelope
    from opencontext_core.runtime.decision_log import DecisionRecorder
    from opencontext_core.runtime.event_bus import EventBus

OperationKind = Literal[
    "file",
    "command",
    "network",
    "provider",
    "secret",
    "memory",
    "plugin",
    "auto_apply",
    "cache",
    "kg_write",
]

# Default forbidden paths/commands mirror ``HarnessConfig`` so the engine has a
# safe deny-list even when no harness config is threaded through.
_DEFAULT_FORBIDDEN_PATHS = [".env", "secrets/", "private/", "vendor/", "node_modules/"]
_DEFAULT_FORBIDDEN_COMMANDS = ["rm -rf", "git push --force", "curl | bash"]

_CI_ENV_VARS = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE", "JENKINS_URL", "OPENCONTEXT_CI")


def detect_ci() -> bool:
    """True when running under a known non-interactive CI/remote environment."""
    return any(os.environ.get(var) for var in _CI_ENV_VARS)


class PolicyOperation(BaseModel):
    """A governed operation submitted to :meth:`PolicyEngine.evaluate`."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    kind: OperationKind
    # command
    command: str | None = None
    # file
    target_path: str | None = None
    # network / provider
    provider: str | None = None
    explicitly_allowlisted: bool = False
    provider_metadata: dict[str, bool] | None = None
    items: list[Any] = Field(default_factory=list)
    # secret / memory / kg_write
    text: str | None = None
    classification: str | None = None
    # cache
    classifications: tuple[str, ...] | None = None
    # plugin
    requested_capability: str | None = None
    plugin_allowlist: list[str] = Field(default_factory=list)
    # auto_apply
    changed_paths: list[str] = Field(default_factory=list)
    has_deletes: bool = False
    touches_network_or_export: bool = False
    touches_public_api: bool = False
    has_tests: bool = True


class PolicyEngine:
    """Single evaluation entry point delegating to the existing enforcers."""

    contract_version = POLICY_CONTRACT_VERSION

    def __init__(
        self,
        *,
        preset: PolicyPreset | str | None = None,
        config: OpenContextConfig | None = None,
        ci_mode: bool | None = None,
        event_bus: EventBus | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        envelope: RunEnvelope | None = None,
        recorder: DecisionRecorder | None = None,
        forbidden_paths: list[str] | None = None,
        forbidden_commands: list[str] | None = None,
        command_enforcement: bool | None = None,
    ) -> None:
        self._config = config
        self._preset = self._resolve_preset(preset, config)
        self._posture: PresetPosture = posture_for(self._preset)
        self._security_mode = self._resolve_security_mode(config)
        self._ci_mode = detect_ci() if ci_mode is None else ci_mode
        self._bus = event_bus
        self._session_id = session_id or "policy-session"
        self._run_id = run_id
        self._envelope = envelope
        self._recorder = recorder
        self._forbidden_paths = (
            forbidden_paths if forbidden_paths is not None else list(_DEFAULT_FORBIDDEN_PATHS)
        )
        self._forbidden_commands = (
            forbidden_commands
            if forbidden_commands is not None
            else list(_DEFAULT_FORBIDDEN_COMMANDS)
        )
        self._command_enforcement = (
            self._posture.command_enforcement
            if command_enforcement is None
            else command_enforcement
        )
        self._classifier = CommandClassifier()
        self._scanner = SecretScanner()

    # -- public API ---------------------------------------------------------

    @property
    def preset(self) -> PolicyPreset:
        return self._preset

    @property
    def ci_mode(self) -> bool:
        return self._ci_mode

    def evaluate(self, operation: PolicyOperation) -> PolicyDecision:
        """Evaluate one governed operation into a canonical decision (PE-1)."""
        decision = self._dispatch(operation)
        decision = self._finalize(decision)
        self._record(decision)
        emit_policy_events(
            self._bus,
            session_id=self._session_id,
            decision=decision,
            run_id=self._run_id,
        )
        return decision

    # -- dispatch -----------------------------------------------------------

    def _dispatch(self, operation: PolicyOperation) -> PolicyDecision:
        handler = {
            "file": self._eval_file,
            "command": self._eval_command,
            "network": self._eval_network,
            "provider": self._eval_provider,
            "secret": self._eval_secret,
            "memory": self._eval_memory,
            "plugin": self._eval_plugin,
            "auto_apply": self._eval_auto_apply,
            "cache": self._eval_cache,
            "kg_write": self._eval_kg_write,
        }[operation.kind]
        return handler(operation)

    # -- MET branches (delegate, no new denials) ---------------------------

    def _eval_file(self, operation: PolicyOperation) -> PolicyDecision:
        """FILE-1 — delegate to the forbidden-path matcher (single source)."""
        # Lazy import: ``harness.phases`` is heavy and will itself call the engine
        # for commands — importing it here keeps the dependency one-directional.
        from opencontext_core.harness.phases import _path_is_forbidden

        path = operation.target_path or ""
        if self._posture.block_forbidden_paths and _path_is_forbidden(
            path.lstrip("/"), self._forbidden_paths
        ):
            return self._decision(
                "file",
                "deny",
                "forbidden_path",
                "policy.file",
                evidence=[f"path:{path}"],
                remediation="Write to a non-forbidden path or remove it from forbidden_paths.",
            )
        return self._decision(
            "file", "allow", "path_allowed", "policy.file", evidence=[f"path:{path}"]
        )

    def _eval_network(self, operation: PolicyOperation) -> PolicyDecision:
        """NET-1 — delegate to the fail-closed action evaluator."""
        action = evaluate_action(
            ActionRequest(
                action=ActionType.NETWORK,
                explicitly_allowlisted=operation.explicitly_allowlisted,
            ),
            security_mode=self._security_mode,
        )
        return self._from_action(action, "network", "policy.network")

    def _eval_provider(self, operation: PolicyOperation) -> PolicyDecision:
        """PROV-1 — delegate to ContextFirewall.check_provider_call."""
        if self._config is None:
            return self._decision(
                "provider",
                "deny",
                "provider_policy_requires_config",
                "policy.provider",
                remediation="Construct the engine with a config to evaluate provider calls.",
            )
        from opencontext_core.safety.firewall import ContextFirewall

        firewall = ContextFirewall(self._config)
        result = firewall.check_provider_call(
            operation.provider or "",
            list(operation.items),
            provider_metadata=operation.provider_metadata,
        )
        if result.allowed:
            return self._decision(
                "provider",
                "allow",
                result.reason,
                "policy.provider",
                evidence=[f"provider:{operation.provider}"],
            )
        return self._decision(
            "provider",
            "deny",
            result.reason,
            "policy.provider",
            evidence=[f"provider:{operation.provider}"],
            remediation="Redact the payload, allowlist the provider, or use a local provider.",
        )

    def _eval_secret(self, operation: PolicyOperation) -> PolicyDecision:
        """SECRET-1 — scan; redact-and-warn when possible, else deny."""
        text = self._operation_text(operation)
        findings = self._scanner.scan(text)
        if not findings:
            return self._decision("secret", "allow", "no_secret_detected", "policy.secret")
        kinds = sorted({f.kind for f in findings})
        if self._posture.redact_secrets:
            redacted = self._scanner.redact(text)
            if not self._scanner.scan(redacted):
                return self._decision(
                    "secret",
                    "warn",
                    "secret_redacted",
                    "policy.secret",
                    evidence=[f"secret:{kind}" for kind in kinds],
                )
        return self._decision(
            "secret",
            "deny",
            "raw_secret_detected",
            "policy.secret",
            evidence=[f"secret:{kind}" for kind in kinds],
            remediation="Redact or remove the secret before this sink.",
        )

    def _eval_plugin(self, operation: PolicyOperation) -> PolicyDecision:
        """PLUGIN-1 — deny-by-default allowlist check."""
        capability = operation.requested_capability or ""
        if capability and capability in operation.plugin_allowlist:
            return self._decision(
                "plugin",
                "allow",
                "capability_allowlisted",
                "policy.plugin",
                evidence=[f"capability:{capability}"],
            )
        return self._decision(
            "plugin",
            "deny",
            "undeclared_plugin_capability",
            "policy.plugin",
            evidence=[f"capability:{capability}"],
            remediation="Declare the capability in the plugin manifest allowlist.",
        )

    # -- NEW branches -------------------------------------------------------

    def _eval_command(self, operation: PolicyOperation) -> PolicyDecision:
        """CMD-1/CMD-2 — enforce the deny-list, then classify & adjudicate."""
        command = operation.command or ""
        if self._command_enforcement and self._classifier.is_forbidden(
            command, self._forbidden_commands
        ):
            return self._decision(
                "command",
                "deny",
                "forbidden_command",
                "policy.command",
                evidence=[f"command:{command}"],
                remediation="This command is on forbidden_commands; run an allowed alternative.",
            )
        category = self._classifier.classify(command)
        verb = self._command_verb(category)
        reason = f"command_{category.value}"
        if verb == "deny":
            return self._decision(
                "command",
                "deny",
                reason,
                "policy.command",
                evidence=[f"command:{command}", f"category:{category.value}"],
                remediation="Use a safer command or relax the preset to permit this category.",
            )
        return self._decision(
            "command",
            verb,
            reason,
            "policy.command",
            evidence=[f"command:{command}", f"category:{category.value}"],
            required_approval=(verb == "ask"),
        )

    def _eval_memory(self, operation: PolicyOperation) -> PolicyDecision:
        """MEM-1 — reject chain-of-thought, raw logs, secrets, restricted data."""
        text = self._operation_text(operation)
        forbidden = forbidden_memory_content(text)
        if forbidden is not None:
            return self._decision(
                "memory",
                "deny",
                forbidden,
                "policy.memory",
                remediation="Store a distilled fact, not reasoning or raw logs.",
            )
        classification = (operation.classification or "").strip().lower()
        if classification in {"secret", "regulated"}:
            return self._decision(
                "memory",
                "deny",
                "classification_too_sensitive",
                "policy.memory",
                evidence=[f"classification:{classification}"],
                remediation="Restricted data cannot be stored in memory.",
            )
        if self._scanner.scan(text):
            return self._decision(
                "memory",
                "deny",
                "raw_secret_in_memory",
                "policy.memory",
                remediation="Redact secrets before persisting to memory.",
            )
        return self._decision("memory", "allow", "memory_write_allowed", "policy.memory")

    def _eval_auto_apply(self, operation: PolicyOperation) -> PolicyDecision:
        """AUTO-1 — risk-tiered allow/ask/deny."""
        return AutoApplyPolicy().evaluate(
            changed_paths=list(operation.changed_paths),
            has_deletes=operation.has_deletes,
            touches_network_or_export=operation.touches_network_or_export,
            touches_public_api=operation.touches_public_api,
            has_tests=operation.has_tests,
        )

    def _eval_cache(self, operation: PolicyOperation) -> PolicyDecision:
        """CONV.1 — deny cache of context above the preset classification ceiling."""
        classifications = operation.classifications or ("internal",)
        ceiling = self._posture.cache_ceiling
        over = [c for c in classifications if exceeds_ceiling(c, ceiling)]
        if over:
            return self._decision(
                "cache",
                "deny",
                "classification_above_cache_ceiling",
                "policy.cache",
                evidence=[f"classification:{c}" for c in over],
                remediation=f"Do not cache context above the '{ceiling}' ceiling.",
            )
        return self._decision("cache", "allow", "cache_allowed", "policy.cache")

    def _eval_kg_write(self, operation: PolicyOperation) -> PolicyDecision:
        """CONV.2 — deny/flag secret-bearing symbols before indexing."""
        text = self._operation_text(operation)
        findings = self._scanner.scan(text)
        if findings:
            kinds = sorted({f.kind for f in findings})
            return self._decision(
                "kg_write",
                "deny",
                "secret_in_kg_symbol",
                "policy.kg_write",
                evidence=[f"secret:{kind}" for kind in kinds],
                remediation="Redact the symbol body or exclude it from indexing.",
            )
        return self._decision("kg_write", "allow", "kg_write_allowed", "policy.kg_write")

    # -- helpers ------------------------------------------------------------

    def _command_verb(self, category: CommandCategory) -> str:
        if category in (CommandCategory.SAFE, CommandCategory.TEST, CommandCategory.PKG):
            return "allow"
        if category is CommandCategory.DESTRUCTIVE:
            return self._posture.destructive_command
        if category is CommandCategory.NETWORK:
            return self._posture.network
        return self._posture.unknown_command

    def _operation_text(self, operation: PolicyOperation) -> str:
        if operation.text is not None:
            return operation.text
        parts: list[str] = []
        for item in operation.items:
            content = getattr(item, "content", None)
            if isinstance(content, str):
                parts.append(content)
        return "\n".join(parts)

    def _from_action(self, action: Any, operation: str, policy_id: str) -> PolicyDecision:
        verb = action.as_policy_verb
        remediation = ""
        if verb == "deny":
            remediation = "Explicitly allowlist this operation or relax the security mode."
        return self._decision(
            operation,
            verb,
            action.reason,
            policy_id,
            required_approval=action.requires_approval,
            remediation=remediation,
        )

    def _decision(
        self,
        operation: str,
        verb: str,
        reason: str,
        policy_id: str,
        *,
        evidence: list[str] | None = None,
        required_approval: bool = False,
        remediation: str = "",
    ) -> PolicyDecision:
        return PolicyDecision(
            operation=operation,
            decision=verb,  # type: ignore[arg-type]
            reason=reason,
            policy_id=policy_id,
            evidence_refs=evidence or [],
            required_approval=required_approval or verb == "ask",
            remediation=remediation,
            mode="ci" if self._ci_mode else "interactive",
        )

    def _finalize(self, decision: PolicyDecision) -> PolicyDecision:
        """Apply the CI fail-closed downgrade and guarantee actionable denials."""
        # CONV.4: no human can approve in CI/remote — an ``ask`` becomes ``deny``.
        if self._ci_mode and decision.decision == "ask":
            decision = decision.model_copy(
                update={
                    "decision": "deny",
                    "reason": f"{decision.reason}:ci_fail_closed",
                    "required_approval": False,
                    "remediation": decision.remediation
                    or "Approval cannot be granted in CI/remote mode; apply interactively.",
                    "mode": "ci",
                }
            )
        # CONV.5: every deny carries an actionable remediation.
        if decision.decision == "deny" and not decision.remediation:
            decision = decision.model_copy(
                update={
                    "remediation": f"Denied by {decision.policy_id} ({decision.reason}); "
                    "adjust the preset or request approval.",
                }
            )
        return decision

    def _record(self, decision: PolicyDecision) -> None:
        """Append the decision to the run envelope and Decision Log (CONV.5)."""
        if self._envelope is not None:
            self._envelope.policy_decisions.append(decision.to_envelope())
        if self._recorder is not None:
            from opencontext_core.runtime.decisions import RuntimeDecision

            self._recorder.record(
                RuntimeDecision(
                    kind="policy",
                    chosen=decision.decision,
                    reason=decision.reason,
                    governed_by="policy",
                    run_id=self._run_id,
                ),
                policy_ref=decision.decision_id,
            )

    def _resolve_preset(
        self, preset: PolicyPreset | str | None, config: OpenContextConfig | None
    ) -> PolicyPreset:
        if preset is not None:
            return resolve_preset(preset)
        policy_cfg = getattr(config, "policy", None) if config is not None else None
        configured = getattr(policy_cfg, "preset", None) if policy_cfg is not None else None
        if configured:
            return resolve_preset(configured)
        if config is not None:
            return preset_from_security_mode(config.security.mode)
        return resolve_preset(None)

    def _resolve_security_mode(self, config: OpenContextConfig | None) -> SecurityMode:
        if config is not None:
            return config.security.mode
        return security_mode_for_preset(self._preset)
