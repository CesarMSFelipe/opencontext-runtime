"""Fail-closed action policy decisions for the controlled agentic layer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum
from opencontext_core.config import SecurityMode


class ActionType(StrEnum):
    """Permission classes for runtime actions."""

    READ_CONTEXT = "READ_CONTEXT"
    READ_FILE = "READ_FILE"
    READ_TRACE = "READ_TRACE"
    READ_GIT_DIFF = "READ_GIT_DIFF"
    RUN_SAFE_COMMAND = "RUN_SAFE_COMMAND"
    RUN_TEST = "RUN_TEST"
    RUN_LINTER = "RUN_LINTER"
    CALL_LLM = "CALL_LLM"
    CALL_TOOL = "CALL_TOOL"
    WRITE_FILE = "WRITE_FILE"
    NETWORK = "NETWORK"
    MCP_TOOL = "MCP_TOOL"
    EXPORT_CONTEXT = "EXPORT_CONTEXT"


class ApprovalLevel(StrEnum):
    """Policy outcome before caller approval is applied."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class ActionRequest(BaseModel):
    """Description of one proposed agentic action."""

    model_config = ConfigDict(extra="forbid")

    action: ActionType = Field(description="Action class being requested.")
    explicitly_allowlisted: bool = Field(
        default=False,
        description="Whether the exact tool, command, or provider route is allowlisted.",
    )
    approved: bool = Field(
        default=False,
        description="Whether a human approval gate has approved this action.",
    )
    sanitized: bool = Field(
        default=True,
        description="Whether trace/export/context payloads are sanitized before the sink.",
    )
    sandbox_enabled: bool = Field(
        default=False,
        description="Whether an explicit sandbox boundary is active for write-like actions.",
    )
    external_provider: bool = Field(
        default=False,
        description="Whether CALL_LLM routes outside the local/mock provider boundary.",
    )


class ActionPolicyDecision(BaseModel):
    """Traceable decision for one proposed action."""

    model_config = ConfigDict(extra="forbid")

    action: ActionType = Field(description="Action class that was evaluated.")
    decision: ApprovalLevel = Field(description="Base policy decision.")
    allowed: bool = Field(description="Whether the action may proceed now.")
    requires_approval: bool = Field(description="Whether human approval is required.")
    reason: str = Field(description="Stable policy reason.")

    @property
    def as_policy_verb(self) -> str:
        """Map this decision onto a canonical PolicyDecision verb (PR-005 adapter).

        ``ApprovalLevel`` already uses the canonical ``allow``/``ask``/``deny``
        values, so the unified ``PolicyEngine`` surfaces the fail-closed defaults
        here unchanged (no upward import — the engine wraps this verb into its
        ``policy.models.PolicyDecision``). PE-4 parity: a default-denied action
        maps to ``deny``.
        """
        return self.decision.value


_DEFAULT_ACTIONS: dict[ActionType, ApprovalLevel] = {
    ActionType.READ_CONTEXT: ApprovalLevel.ALLOW,
    ActionType.READ_FILE: ApprovalLevel.ALLOW,
    ActionType.READ_TRACE: ApprovalLevel.ALLOW,
    ActionType.READ_GIT_DIFF: ApprovalLevel.ALLOW,
    ActionType.RUN_SAFE_COMMAND: ApprovalLevel.ASK,
    ActionType.RUN_TEST: ApprovalLevel.ASK,
    ActionType.RUN_LINTER: ApprovalLevel.ASK,
    ActionType.CALL_LLM: ApprovalLevel.ASK,
    ActionType.CALL_TOOL: ApprovalLevel.DENY,
    ActionType.WRITE_FILE: ApprovalLevel.DENY,
    ActionType.NETWORK: ApprovalLevel.DENY,
    ActionType.MCP_TOOL: ApprovalLevel.DENY,
    ActionType.EXPORT_CONTEXT: ApprovalLevel.ALLOW,
}


def evaluate_action(
    request: ActionRequest,
    *,
    security_mode: SecurityMode = SecurityMode.PRIVATE_PROJECT,
) -> ActionPolicyDecision:
    """Evaluate a proposed action using secure defaults."""

    if security_mode is SecurityMode.AIR_GAPPED and request.action in {
        ActionType.NETWORK,
        ActionType.MCP_TOOL,
    }:
        return _deny(request.action, "air_gapped_blocks_network_and_mcp")

    if request.action is ActionType.READ_TRACE and not request.sanitized:
        return _deny(request.action, "raw_trace_access_denied")

    if request.action is ActionType.EXPORT_CONTEXT and not request.sanitized:
        return _deny(request.action, "raw_context_export_denied")

    if request.action is ActionType.CALL_LLM:
        if request.external_provider:
            if security_mode is SecurityMode.AIR_GAPPED:
                return _deny(request.action, "air_gapped_blocks_external_provider")
            if not request.explicitly_allowlisted:
                return _deny(request.action, "external_provider_not_allowlisted")
            return _ask(request, "external_provider_requires_approval")
        return _allow(request.action, "local_or_mock_provider")

    if request.action is ActionType.CALL_TOOL:
        if not request.explicitly_allowlisted:
            return _deny(request.action, "tool_not_allowlisted")
        return _ask(request, "allowlisted_tool_requires_approval")

    if request.action is ActionType.WRITE_FILE:
        if not request.sandbox_enabled:
            return _deny(request.action, "write_requires_explicit_sandbox")
        if not request.explicitly_allowlisted:
            return _deny(request.action, "write_target_not_allowlisted")
        return _ask(request, "sandboxed_write_requires_approval")

    level = _DEFAULT_ACTIONS[request.action]
    if level is ApprovalLevel.ALLOW:
        return _allow(request.action, "default_allow")
    if level is ApprovalLevel.ASK:
        return _ask(request, "default_requires_approval")
    return _deny(request.action, "default_deny")


def _allow(action: ActionType, reason: str) -> ActionPolicyDecision:
    return ActionPolicyDecision(
        action=action,
        decision=ApprovalLevel.ALLOW,
        allowed=True,
        requires_approval=False,
        reason=reason,
    )


def _ask(request: ActionRequest, reason: str) -> ActionPolicyDecision:
    return ActionPolicyDecision(
        action=request.action,
        decision=ApprovalLevel.ASK,
        allowed=request.approved,
        requires_approval=not request.approved,
        reason="approved" if request.approved else reason,
    )


def _deny(action: ActionType, reason: str) -> ActionPolicyDecision:
    return ActionPolicyDecision(
        action=action,
        decision=ApprovalLevel.DENY,
        allowed=False,
        requires_approval=False,
        reason=reason,
    )
