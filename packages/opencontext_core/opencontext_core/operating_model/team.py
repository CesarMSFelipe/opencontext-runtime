"""Team commands, approvals, baselines, policy diffs, and run receipts."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.paths import StorageMode, resolve_workspace_path


class ApprovalDecision(BaseModel):
    """Human approval decision."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Approval id.")
    kind: str = Field(description="Approval kind.")
    status: str = Field(default="pending", description="pending, approved, or denied.")
    reason: str = Field(default="", description="Decision reason.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    decided_at: datetime | None = Field(default=None, description="Decision timestamp.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Approval metadata.")


class TeamCommandRegistry:
    """Registry for shared team commands."""

    def __init__(self, commands: dict[str, dict[str, Any]] | None = None) -> None:
        self.commands = commands or {}

    def list(self) -> list[str]:
        """List command names."""

        return sorted(self.commands)

    def get(self, name: str) -> dict[str, Any]:
        """Return a command definition."""

        return dict(self.commands.get(name, {"status": "scaffold", "name": name}))


class HookRegistry:
    """Registry for workflow hooks."""

    def __init__(self, hooks: dict[str, list[str]] | None = None) -> None:
        self.hooks = hooks or {}

    def hooks_for(self, event: str) -> list[str]:
        """Return hook names for an event."""

        return list(self.hooks.get(event, []))


class HumanApprovalNode:
    """Workflow node that requires explicit approval before continuing."""

    def require(self, kind: str, reason: str) -> ApprovalDecision:
        """Create a pending approval decision."""

        return ApprovalDecision(id=f"apr-{uuid4().hex[:12]}", kind=kind, reason=reason)


class TeamPlaybookRegistry:
    """File-backed playbook registry scaffold."""

    def __init__(self, root: Path | str = ".opencontext/playbooks") -> None:
        self.root = Path(root)

    def list(self) -> list[str]:
        """List local playbooks."""

        if not self.root.exists():
            return []
        return sorted(path.stem for path in self.root.glob("*.yaml"))

    def explain(self, name: str) -> dict[str, Any]:
        """Return playbook metadata."""

        path = self.root / f"{name}.yaml"
        return {"name": name, "path": str(path), "exists": path.exists(), "execution": "scaffold"}


class OrgBaselineChecker:
    """Checks security-relevant org baseline values."""

    def check(self, config: dict[str, Any]) -> list[str]:
        """Return baseline violations."""

        violations: list[str] = []
        if config.get("security", {}).get("external_providers_enabled") is True:
            violations.append("external_providers_enabled")
        if config.get("tools", {}).get("mcp", {}).get("enabled") is True:
            violations.append("mcp_enabled")
        if config.get("traces", {}).get("store_raw_context") is True:
            violations.append("raw_traces_enabled")
        if config.get("cache", {}).get("semantic", {}).get("enabled") is True:
            violations.append("semantic_cache_enabled")
        return violations


class PolicyDiffEngine:
    """Detects risky policy changes from before/after config snippets."""

    RISK_KEYS: tuple[str, ...] = (
        "external_providers_enabled",
        "store_raw_context",
        "enabled: true",
        "semantic",
    )

    def diff_text(self, before: str, after: str) -> list[str]:
        """Return risky policy-change labels."""

        risks: list[str] = []
        provider_enabled = "external_providers_enabled: true"
        if provider_enabled not in before and provider_enabled in after:
            risks.append("external_provider_enabled")
        if "store_raw_context: true" not in before and "store_raw_context: true" in after:
            risks.append("raw_trace_enabled")
        if "mcp:" in after and "enabled: true" in after and "mcp:" not in before:
            risks.append("mcp_may_be_enabled")
        return risks


class ApprovalInbox:
    """In-memory approval queue scaffold."""

    def __init__(self) -> None:
        self.items: dict[str, ApprovalDecision] = {}

    def add(self, decision: ApprovalDecision) -> None:
        """Add a pending approval."""

        self.items[decision.id] = decision

    def decide(self, approval_id: str, status: str) -> ApprovalDecision:
        """Approve or deny an item."""

        current = self.items[approval_id]
        updated = current.model_copy(update={"status": status})
        self.items[approval_id] = updated
        return updated

    def list(self) -> list[ApprovalDecision]:
        """List approvals."""

        return sorted(self.items.values(), key=lambda item: item.id)


class PersistentApprovalInbox:
    """JSON-file backed approval inbox under `.opencontext/approvals`."""

    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root)
        self.base_path = resolve_workspace_path(self.root, StorageMode.local) / "approvals"
        self.base_path.mkdir(parents=True, exist_ok=True)

    def add(self, decision: ApprovalDecision) -> ApprovalDecision:
        """Persist a pending approval decision."""

        self._write(decision)
        return decision

    def request(
        self,
        *,
        kind: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> ApprovalDecision:
        """Create and persist a pending approval."""

        decision = ApprovalDecision(
            id=f"apr-{uuid4().hex[:12]}",
            kind=kind,
            reason=reason,
            metadata=metadata or {},
        )
        return self.add(decision)

    def get(self, approval_id: str) -> ApprovalDecision:
        """Load one approval by id."""

        path = self.base_path / f"{approval_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Approval not found: {approval_id}")
        return ApprovalDecision.model_validate_json(path.read_text(encoding="utf-8"))

    def decide(self, approval_id: str, status: str) -> ApprovalDecision:
        """Approve or deny an item and persist the decision."""

        if status not in {"approved", "denied"}:
            raise ValueError(f"Unsupported approval status: {status}")
        current = self.get(approval_id)
        updated = current.model_copy(update={"status": status, "decided_at": datetime.now(tz=UTC)})
        self._write(updated)
        return updated

    def list(self, *, status: str | None = None) -> list[ApprovalDecision]:
        """List persisted approvals."""

        items = [
            ApprovalDecision.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.base_path.glob("*.json"))
        ]
        return [item for item in items if status is None or item.status == status]

    def _write(self, decision: ApprovalDecision) -> Path:
        path = self.base_path / f"{decision.id}.json"
        path.write_text(decision.model_dump_json(indent=2), encoding="utf-8")
        return path


class RunReceipt(BaseModel):
    """Audit receipt for one run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="opencontext.run_receipt.v2")
    run_id: str = Field(description="Run id.")
    workflow_id: str = Field(description="Workflow id.")
    policy_hash: str = Field(description="Policy hash.")
    context_pack_hash: str = Field(description="Context pack hash.")
    prompt_hash: str = Field(description="Prompt hash.")
    provider: str = Field(description="Requested provider.")
    model: str = Field(description="Requested model.")
    actual_provider: str | None = Field(default=None)
    actual_model: str | None = Field(default=None)
    model_hint_honored: bool | None = Field(default=None)
    envelope_hash: str | None = Field(default=None)
    artifacts_hash: str | None = Field(default=None)
    trace_id: str = Field(description="Trace id.")
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    security_decisions: list[str] = Field(default_factory=list)
    cache_decisions: list[str] = Field(default_factory=list)
    policy_decisions: list[str] = Field(default_factory=list)
    tool_decisions: list[str] = Field(default_factory=list)
    quality_status: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class RunReceiptGenerator:
    """Generates traceable run receipts without storing raw prompt text."""

    def generate(
        self,
        *,
        workflow_id: str,
        policy: str,
        context_pack: str,
        prompt: str,
        provider: str,
        model: str,
        trace_id: str,
        input_tokens: int,
        output_tokens: int,
        quality_status: str | None = None,
    ) -> RunReceipt:
        """Generate a receipt from hashed artifacts.

        ``quality_status`` (optional) records the run's quality-gate verdict so a
        receipt carries the verification outcome, not just token/security facts.
        """

        return RunReceipt(
            run_id=f"run-{uuid4().hex[:12]}",
            workflow_id=workflow_id,
            policy_hash=_hash(policy),
            context_pack_hash=_hash(context_pack),
            prompt_hash=_hash(prompt),
            provider=provider,
            model=model,
            trace_id=trace_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            quality_status=quality_status,
        )


class TeamReportGenerator:
    """Generates compact team report scaffolds."""

    def generate(self, kind: str) -> dict[str, Any]:
        """Return report scaffold metadata."""

        return {
            "kind": kind,
            "status": "scaffold",
            "includes": ["cost", "security", "quality", "token_savings"],
        }


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
