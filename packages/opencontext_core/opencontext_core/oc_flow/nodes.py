"""OC Flow node handlers + the work-producing executor seam (PR-007, FLOW-3,
FLOW-4, FLOW-5, FLOW-6, FLOW-7, FLOW-8, FLOW-13, FLOW-14, book doc 04 §7-§14).

Each node is a pure handler ``node_<name>(ctx) -> NodeResult`` returning its outputs
and a typed outcome; the runner dispatches them and resolves the next node from the
outcome. The actual reasoning (build a contract, propose edits, form hypotheses) is
delegated to a :class:`NodeExecutor` — the typed seam a provider-backed
implementation fills later. The default :class:`DeterministicNodeExecutor` produces
honest, model-free artifacts so OC Flow runs end-to-end with no LLM configured
(matching the harness's planned/executor-absent behaviour).

Exit-condition guards (book §7-§11) are explicit predicates the runner checks before
transitioning out of a node — a node that has not met its contract refuses to advance.

Layering (doc 58): L9 composing L2 (checkpoint), agents executor (ApplyEdit) and the
OC Flow models/inspection downward.
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from opencontext_core.actions.policy import ActionRequest, ActionType, evaluate_action
from opencontext_core.agents.executor import ApplyEdit, ApplyOperation, apply_edit
from opencontext_core.config import SecurityMode
from opencontext_core.errors import ProviderError
from opencontext_core.harness.checkpoint import CheckpointStore
from opencontext_core.models.llm import LLMRequest
from opencontext_core.oc_flow.budgets import OC_FLOW_BUDGETS, lane_config
from opencontext_core.oc_flow.inspection import run_local_inspection
from opencontext_core.oc_flow.models import (
    ContextEnvelope,
    ContextEnvelopeItem,
    DiagnosisAttempt,
    EscalationReport,
    Hypothesis,
    InspectionReport,
    Lane,
    NodeOutcome,
    TaskContract,
)
from opencontext_core.safety.secrets import SecretScanner


class OCFlowError(RuntimeError):
    """Raised when a node cannot satisfy its contract (e.g. refused transition)."""


@dataclass
class NodeResult:
    """The output of a node handler: outputs, the typed outcome and token spend."""

    node: str
    outcome: NodeOutcome
    outputs: dict[str, Any] = field(default_factory=dict)
    llm_tokens: int = 0
    artifacts: list[str] = field(default_factory=list)


@dataclass
class OCFlowContext:
    """Mutable run context threaded through the node handlers."""

    root: Path
    artifacts_dir: Path
    task: str
    lane: Lane
    profile: str | None
    executor: NodeExecutor
    max_attempts: int
    seed_paths: list[str] = field(default_factory=list)
    requested_edits: list[ApplyEdit] = field(default_factory=list)
    cache: Any | None = None  # SemanticCache (L4) — optional, advisory.
    run_external_inspection: bool = False
    test_command: list[str] | None = None
    lint_command: list[str] | None = None
    typecheck_command: list[str] | None = None
    # PR-008 KG v2 (flag-gated, default off): when enabled and a graph DB exists,
    # gather_context consults the KG subgraph before broad file reads (KG-09/14).
    kg_v2_enabled: bool = False
    graph_db_path: Path | None = None
    kg_observer: Any | None = None  # optional KgObserver for kg.* events/receipts
    # PR-010 Context Engine v2 (flag-gated, default off): when enabled, gather_context
    # assembles the canonical three-layer ContextEnvelope via the ContextEngine and
    # projects it onto the surgical seam; with the flag off the legacy path runs.
    context_engine_enabled: bool = False
    # B1 / AVH-011: whether the task implies a code/file mutation. Threaded into the
    # inspection scope gate (no-op on a mutation task is blocking) and the post-graph
    # completion gate (a no-op mutation may never report `completed`).
    mutation_required: bool = False
    # Memory parity (SDD ExplorePhase/ArchivePhase): when ``memory_enabled`` and a
    # store is resolvable, gather_context folds prior memory recall into the envelope
    # and consolidation persists the memory delta through the harvester/harness path.
    # A missing store degrades to a recorded omission / no-op reason, never an error.
    memory_enabled: bool = False
    memory_store: Any | None = None  # AgentMemoryStore (duck-typed port)
    memory_harvest_enabled: bool = False  # memory.harvest_after_run
    # MEMORY_CONTRACT rule 4: recall hits recorded by _fold_memory_recall and
    # persisted into run.json's memory block ({id, type, score, used_for}).
    memory_hits: list[dict[str, Any]] = field(default_factory=list)
    # MEMORY_CONTRACT rule 4 (candidate accounting): how many memory candidates
    # this run harvested (set by _persist_memory_delta) and whether the project
    # config gates new memory behind approval (memory.approval_required,
    # threaded by the runner). Both feed run.json's memory block additively.
    memory_new_candidates: int = 0
    memory_approval_required: bool = False
    # Strict-TDD posture threaded from the runner (config.harness.tdd_mode /
    # OPENCONTEXT_TDD_MODE). "strict" enables the RED-first pre-check in node_mutate;
    # "ask"/"off" (the default) leave the flow's behaviour byte-for-byte unchanged.
    tdd_mode: str = "ask"
    # RED evidence captured by the runner BEFORE the graph walk (exit code of the
    # pre-mutation test run). When set, node_mutate's strict pre-check reuses it
    # instead of re-running the tests.
    tdd_red_exit_code: int | None = None
    memory_v2_enabled: bool = False  # runtime.memory_v2_enabled → MemoryHarness routing
    run_id: str = ""  # run provenance carried into harvested memory records
    # Compression parity (context substrate): when enabled, gather_context runs the
    # CompressionEngine over oversized envelope content (SQLite-KG items honestly
    # skipped) and records the evidence in context-receipt.json.
    compression_enabled: bool = False
    compression_config: Any | None = None  # config.CompressionConfig (None → defaults)

    # live state produced by nodes
    init_done: bool = False
    envelope: ContextEnvelope | None = None
    contract: TaskContract | None = None
    changed_files: list[str] = field(default_factory=list)
    checkpoint_id: str | None = None
    checkpoint: Any | None = None
    inspection: InspectionReport | None = None
    diagnosis_attempts: list[DiagnosisAttempt] = field(default_factory=list)
    failed_strategies: list[str] = field(default_factory=list)
    cache_hits: int = 0
    # B1 / AVH-015: reason the run produced no usable edits (invalid/blocked edit
    # set, policy denial), surfaced by the completion gate and the CLI summary.
    block_reason: str | None = None
    # Policy-gate outcome (RUN_STATE_CONTRACT / DOC2 §10.4): ``policy_blocked`` is
    # True once the action policy refused this run's edits (deny OR unapproved
    # ask); it forbids the repair loop. ``policy_approval_required`` narrows it to
    # the approval flavor — the runner surfaces that terminal as canonical
    # ``needs_approval``.
    policy_blocked: bool = False
    policy_approval_required: bool = False


# --------------------------------------------------------------------- executor seam
class NodeExecutor(Protocol):
    """The work-producing seam OC Flow delegates reasoning to (book §5).

    A provider-backed implementation (future PR) supplies real model output; the
    default deterministic implementation supplies honest, model-free artifacts.
    """

    def gather_context(
        self, task: str, seed_paths: Sequence[str], depth: int
    ) -> ContextEnvelope: ...

    def plan(self, task: str, envelope: ContextEnvelope) -> TaskContract: ...

    def mutate(self, contract: TaskContract, envelope: ContextEnvelope) -> list[ApplyEdit]: ...

    def diagnose(
        self,
        attempt: int,
        contract: TaskContract,
        inspection: InspectionReport,
        failed_strategies: Sequence[str],
    ) -> DiagnosisAttempt: ...


class DeterministicNodeExecutor:
    """Model-free executor: honest, deterministic artifacts (no LLM).

    ``requested_edits`` lets a caller (or the CLI fixture) drive a concrete surgical
    change without a model; without them ``mutate`` proposes no edits (an honest
    no-op patch) rather than fabricating one.
    """

    def __init__(self, requested_edits: list[ApplyEdit] | None = None) -> None:
        self._requested_edits = list(requested_edits or [])

    def gather_context(self, task: str, seed_paths: Sequence[str], depth: int) -> ContextEnvelope:
        items: list[ContextEnvelopeItem] = []
        omissions: list[str] = []
        for rel in list(seed_paths)[: max(1, depth) * 4]:
            items.append(
                ContextEnvelopeItem(
                    source="file",
                    ref=rel,
                    summary=f"seed file for: {task[:60]}",
                    tokens=200,
                    # C17: why_included records source type + selection reason.
                    why_included="file:seed",
                )
            )
        if not items:
            # No seeds resolved — still produce a usable, minimal envelope so the
            # run can proceed, and record the omission (book §8).
            items.append(
                ContextEnvelopeItem(
                    source="memory",
                    ref="task",
                    summary=task[:120],
                    tokens=120,
                    why_included="memory:task-statement-fallback",
                )
            )
            omissions.append("no source files seeded; planning from task statement only")
        return ContextEnvelope(
            task=task,
            items=items,
            omissions=omissions,
            token_estimate=sum(i.tokens for i in items),
        )

    def plan(self, task: str, envelope: ContextEnvelope) -> TaskContract:
        changed = [i.ref for i in envelope.items if i.source == "file"]
        return TaskContract(
            scope=task,
            non_scope=["unrelated modules", "architecture redesign", "public API changes"],
            acceptance_criteria=[f"the task is addressed: {task[:120]}"],
            constraints=["surgical change only", "no broad refactor"],
            changed_areas=changed,
            verification_plan=["run local inspection (syntax, secrets, tests)"],
            risk_flags=[],
            stop_conditions=["scope grows beyond OC Flow bounds"],
        )

    def mutate(self, contract: TaskContract, envelope: ContextEnvelope) -> list[ApplyEdit]:
        edits: list[ApplyEdit] = []
        for edit in self._requested_edits:
            # Ensure every edit carries a reason + acceptance-criterion ref (FLOW-7).
            reason = edit.reason or f"surgical change for: {contract.scope[:80]}"
            refs = edit.requirement_refs or list(contract.acceptance_criteria[:1])
            edits.append(edit.model_copy(update={"reason": reason, "requirement_refs": refs}))
        # Emit the requested edits once; re-entry from a diagnose loop proposes no
        # new edits (the deterministic executor has no model to invent a fix).
        self._requested_edits = []
        return edits

    def diagnose(
        self,
        attempt: int,
        contract: TaskContract,
        inspection: InspectionReport,
        failed_strategies: Sequence[str],
    ) -> DiagnosisAttempt:
        failure = inspection.failure_summary or "unknown failure"
        # Three candidate strategies; pick the first not already ruled out (book §12
        # "never repeat a failed strategy").
        candidates = [
            "correct the failing assertion / off-by-one in the changed code",
            "fix the import or symbol resolution in the changed scope",
            "adjust the test fixture or expected value to the new behaviour",
        ]
        hypotheses = [
            Hypothesis(statement=c, evidence=failure[:160], confidence=0.5 - 0.1 * idx)
            for idx, c in enumerate(candidates)
        ]
        selected = 0
        for idx, c in enumerate(candidates):
            if c not in failed_strategies:
                selected = idx
                break
        return DiagnosisAttempt(
            attempt=attempt,
            reproduction_command="python -m pytest -q (changed scope)",
            reproduction_result=failure[:200],
            hypotheses=hypotheses,
            selected_hypothesis=selected,
            fix_strategy=candidates[selected],
        )


# ------------------------------------------------------- productive provider executor
class _ProviderClient(Protocol):
    """Minimal duck type for a provider gateway: ``generate(request).content``.

    Satisfied by :class:`opencontext_core.providers.gateway.ProviderGateway` and by
    any deterministic test stub — so the productive executor is fully injectable and
    the full pipeline (provider -> validate -> policy -> apply) is exercised honestly.
    """

    def generate(self, request: LLMRequest) -> Any: ...


# Instruction framing the provider's mutation as a strict ApplyEdit JSON array.
_APPLY_EDIT_INSTRUCTION = (
    "Implement the task below as concrete file edits. Output ONLY a JSON array of "
    "ApplyEdit objects, nothing else: "
    '[{"path":"<root-relative>","operation":"replace_range|insert_after|delete_range'
    '|create_file|delete_file","start_line":1,"end_line":3,"content":"<new content>",'
    '"reason":"<why>","requirement_refs":["<criterion>"]}]. '
    "Use surgical line anchors; no prose, no Markdown fences, nothing outside the array."
)


# Generic endpoint URLs (http/https/ws/wss/ftp/...) so a provider transport error
# never leaks an endpoint into a user-visible block_reason.
_URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s'\"<>]+", re.IGNORECASE)


def _redact_provider_error(exc: Exception) -> str:
    """Redact secrets, credentials and endpoint URLs from a provider error.

    Reuses the repository's :class:`SecretScanner` (API keys, tokens, connection
    strings, JWTs) and additionally strips generic endpoint URLs. The resulting
    string is honest about the failure mode but never carries a secret or an
    endpoint; the raw, unredacted exception is reserved for ``--strict`` output.
    """
    from opencontext_core.safety.secrets import SecretScanner

    redacted = SecretScanner().redact(str(exc))
    return _URL_RE.sub("[REDACTED:url]", redacted)


def _parse_apply_edit_set(text: str) -> list[ApplyEdit] | None:
    """Parse a provider response into a validated ``list[ApplyEdit]``.

    Returns the validated edits on success, or ``None`` when the response is
    unparseable or schema-invalid (freeform text, not a JSON array, or any element
    failing :class:`ApplyEdit` validation) — the caller treats ``None`` as a hard
    block (never silently completed). An empty array parses to ``[]`` (a valid but
    empty set: the provider proposed no edits).
    """
    from pydantic import ValidationError

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    edits: list[ApplyEdit] = []
    for item in data:
        if not isinstance(item, dict):
            return None
        try:
            edit = ApplyEdit.model_validate(item)
        except ValidationError:
            return None
        if _invalid_edit_contract_reason(edit):
            return None
        edits.append(edit)
    return edits


def _invalid_edit_contract_reason(edit: ApplyEdit) -> str | None:
    if edit.operation in (ApplyOperation.REPLACE_RANGE, ApplyOperation.DELETE_RANGE):
        if edit.start_line is None or edit.end_line is None:
            return f"{edit.operation.value} requires start_line and end_line"
        if edit.start_line < 1 or edit.end_line < edit.start_line:
            return "invalid line range"
    if edit.operation == ApplyOperation.INSERT_AFTER:
        if edit.after_line is None or edit.after_line < 0:
            return "insert_after requires non-negative after_line"
    return None


def _write_approval_granted(root: Path) -> bool:
    """Whether writes are pre-approved for non-interactive runs at ``root``.

    EXE-POLICIES: ``policies.writes.require_approval`` (overlaid onto
    ``harness.approval_required_for_writes``) is the supported opt-in. When the
    config demands approval, `opencontext run` has no interactive approval gate,
    so the write policy evaluates as ASK-not-approved and the run surfaces
    canonical ``needs_approval``. A missing/invalid config keeps the default
    (approved — OC Flow mutates under a rollback checkpoint).
    """
    try:
        from opencontext_core.config import load_config_or_defaults
        from opencontext_core.config_resolver import resolve_config_path

        config = load_config_or_defaults(resolve_config_path(root), auto_detect=False)
        return not bool(getattr(config.harness, "approval_required_for_writes", False))
    except Exception:
        return True


def _unsafe_edit_reason(edit: ApplyEdit) -> str | None:
    """Pre-apply denylist + proposed-content secret scan."""
    path = Path(edit.path)
    parts = path.parts
    if path.name == ".env" or path.suffix in {".pem", ".key"} or (parts and parts[0] == "secrets"):
        return "forbidden secret-bearing path"
    findings = SecretScanner().scan_secret_findings(edit.content or "")
    if findings:
        kinds = ", ".join(sorted({f.kind for f in findings}))
        return f"secret(s) detected in proposed content ({kinds})"
    return None


class ProviderBackedNodeExecutor:
    """Productive :class:`NodeExecutor` that mutates via a provider gateway (AVH-015).

    ``gather_context`` / ``plan`` / ``diagnose`` reuse the deterministic, model-free
    artifacts; only ``mutate`` is provider-backed: it asks the injected gateway for a
    STRUCTURED, schema-validated ``ApplyEdit`` set, runs each edit through the action
    policy, and returns the edits for ``node_mutate`` to checkpoint/apply/receipt and
    ``node_local_inspection`` to verify. An unparseable/invalid set or a policy denial
    yields zero edits plus a ``block_reason`` — so the run is blocked, never completed.
    A provider-free executor (no gateway) is the deterministic path and never claims a
    mutation it did not make.
    """

    # The completion gate reads this to distinguish "needs an executor" from "the
    # provider produced nothing" (a configured gateway means an executor exists).
    provider_available = True

    def __init__(
        self,
        *,
        gateway: _ProviderClient,
        root: Path,
        provider: str = "mock",
        model: str = "default",
        security_mode: SecurityMode = SecurityMode.PRIVATE_PROJECT,
        is_allowed_path: Any = None,
        max_output_tokens: int = 6000,
        approval_granted: bool | None = None,
    ) -> None:
        self._gateway = gateway
        self._root = Path(root)
        self._provider = provider
        self._model = model
        self._security_mode = security_mode
        self._is_allowed_path = is_allowed_path
        self._max_output_tokens = max_output_tokens
        self._fallback = DeterministicNodeExecutor()
        self.block_reason: str | None = None
        # Policy-gate flags read by node_mutate (RUN_STATE_CONTRACT): approval
        # resolves from the project config unless the caller decides explicitly.
        self._approval_granted = (
            _write_approval_granted(self._root) if approval_granted is None else approval_granted
        )
        self.policy_blocked = False
        self.policy_approval_required = False

    # gather / plan / diagnose: honest, model-free artifacts (mutation is the model job)
    def gather_context(self, task: str, seed_paths: Sequence[str], depth: int) -> ContextEnvelope:
        return self._fallback.gather_context(task, seed_paths, depth)

    def plan(self, task: str, envelope: ContextEnvelope) -> TaskContract:
        return self._fallback.plan(task, envelope)

    def diagnose(
        self,
        attempt: int,
        contract: TaskContract,
        inspection: InspectionReport,
        failed_strategies: Sequence[str],
    ) -> DiagnosisAttempt:
        return self._fallback.diagnose(attempt, contract, inspection, failed_strategies)

    # mutate: provider -> schema-validate -> policy (the productive path)
    def mutate(self, contract: TaskContract, envelope: ContextEnvelope) -> list[ApplyEdit]:
        self.block_reason = None
        self.provider_available = True
        self.policy_blocked = False
        self.policy_approval_required = False
        prompt = (
            f"{_APPLY_EDIT_INSTRUCTION}\n\nTask: {contract.scope}\n"
            f"Acceptance: {'; '.join(contract.acceptance_criteria)}"
        )
        request = LLMRequest(
            prompt=prompt,
            system_prompt="",
            provider=self._provider,
            model=self._model,
            max_output_tokens=self._max_output_tokens,
            metadata={"role": "generate", "phase": "mutate", "workflow": "oc-flow"},
        )
        try:
            response = self._gateway.generate(request)
        except ProviderError:
            # Provider fallback chain exhausted (or no adapter / unsupported capability)
            # at runtime. Catch it here so the failure flows node_mutate ->
            # resolve_completion as a structured `needs_provider`, never a raw traceback
            # in user-visible output. The redacted detail is honest about the failure
            # mode; the raw exception is reserved for --strict.
            self.block_reason = (
                "configured provider failed and fallback unavailable; "
                "next_action=configure a valid provider, disable fallback, or enable MCP sampling"
            )
            # Mark the provider unavailable so the completion gate emits needs_provider
            # (a provider-backed run that produced nothing because the provider failed),
            # not a generic `blocked`.
            self.provider_available = False
            return []
        edits = _parse_apply_edit_set(getattr(response, "content", "") or "")
        if edits is None:
            self.block_reason = "provider returned an unparseable or schema-invalid edit set"
            return []
        if not edits:
            self.block_reason = "provider proposed no edits"
            return []
        # Policy stage: a single denied/forbidden path blocks the WHOLE set so no
        # partial mutation is written (AVH-015 forbidden-path scenario).
        for edit in edits:
            decision = self._policy_decision(edit)
            if not decision.allowed:
                self.policy_blocked = True
                if bool(getattr(decision, "requires_approval", False)):
                    # RUN_STATE_CONTRACT: the policy demands HUMAN APPROVAL before
                    # this write — an approval outcome, not a hard denial. The
                    # runner surfaces it as canonical ``needs_approval``.
                    self.policy_approval_required = True
                    self.block_reason = (
                        f"policy requires human approval before writing to {edit.path}: "
                        f"{decision.reason}"
                    )
                else:
                    self.block_reason = f"policy denied write to {edit.path}: {decision.reason}"
                return []
            if reason := _unsafe_edit_reason(edit):
                self.policy_blocked = True
                self.block_reason = f"policy denied write to {edit.path}: {reason}"
                return []
        # Carry a reason + acceptance-criterion ref on every edit (FLOW-7).
        prepared: list[ApplyEdit] = []
        for edit in edits:
            reason = edit.reason or f"surgical change for: {contract.scope[:80]}"
            refs = edit.requirement_refs or list(contract.acceptance_criteria[:1])
            prepared.append(edit.model_copy(update={"reason": reason, "requirement_refs": refs}))
        return prepared

    def _policy_decision(self, edit: ApplyEdit) -> Any:
        allowlisted = self._allowed(edit.path)
        request = ActionRequest(
            action=ActionType.WRITE_FILE,
            sandbox_enabled=True,  # OC Flow mutates under a rollback checkpoint.
            explicitly_allowlisted=allowlisted,
            # Approval is real, not hardcoded: when the project config demands
            # write approval (policies.writes.require_approval) a non-interactive
            # run is NOT approved and the ASK gate blocks (needs_approval).
            approved=self._approval_granted,
        )
        return evaluate_action(request, security_mode=self._security_mode)

    def _allowed(self, rel: str) -> bool:
        if self._is_allowed_path is not None:
            return bool(self._is_allowed_path(rel))
        # Default allowlist: the path must resolve under root and not target the
        # runtime's own state directory.
        try:
            resolved = (self._root / rel).resolve()
            resolved.relative_to(self._root.resolve())
        except ValueError:
            return False
        parts = Path(rel).parts
        return not (parts and parts[0] == ".opencontext")


class McpSamplingNodeExecutor(ProviderBackedNodeExecutor):
    """Productive executor sourcing its mutation via host MCP sampling (AVH-015).

    MCP sampling is exposed through the same gateway seam (the base gateway preserves
    host MCP sampling), so this reuses the full provider -> validate -> policy ->
    apply pipeline and only differs in provenance. An MCP sampler counts as a
    productive executor (``provider_available = True``) for the completion gate.
    """

    def __init__(self, *, gateway: _ProviderClient, root: Path, **kwargs: Any) -> None:
        super().__init__(gateway=gateway, root=root, provider="mcp", **kwargs)


# ----------------------------------------------------------------------- utilities
def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return path.name


def _budget_for(node: str) -> int:
    """A deterministic per-node token estimate (mid-budget; PR-011 will measure)."""
    lo, hi = OC_FLOW_BUDGETS.get(node, (0, 0))
    return (lo + hi) // 2


def _owner_candidates(root: Path, changed_files: Sequence[str]) -> list[str]:
    """Best-effort owner candidates from git history, with a path fallback."""
    owners: list[str] = []
    for rel in list(changed_files)[:5]:
        try:
            proc = subprocess.run(
                ["git", "log", "-1", "--format=%an", "--", rel],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            name = proc.stdout.strip()
            if name and name not in owners:
                owners.append(name)
        except (OSError, subprocess.TimeoutExpired):
            continue
    if not owners:
        # Fallback: the top package directory of the first changed file.
        for rel in changed_files:
            top = Path(rel).parts[0] if Path(rel).parts else rel
            owners.append(f"maintainers of {top}")
            break
    return owners or ["repository maintainers"]


# -------------------------------------------------------------------- node handlers
def node_init(ctx: OCFlowContext) -> NodeResult:
    """Bind session/profile/policy + persist the init record (book §7)."""
    init = {
        "task": ctx.task,
        "lane": ctx.lane.value,
        "profile": ctx.profile,
        "policy_mode": "default",
        "capabilities_available": True,
        "workflow": "oc-flow",
    }
    name = _write_json(ctx.artifacts_dir / "init.json", init)
    selection = {"workflow": "oc-flow", "reason": "operational task", "lane": ctx.lane.value}
    sel_name = _write_json(ctx.artifacts_dir / "workflow-selection.json", selection)
    ctx.init_done = True
    return NodeResult(
        node="init",
        outcome=NodeOutcome.OK,
        outputs=init,
        llm_tokens=_budget_for("init"),
        artifacts=[name, sel_name],
    )


def node_gather_context(ctx: OCFlowContext) -> NodeResult:
    """Retrieve minimal-sufficient context surgically (book §8, FLOW-CONV).

    PR-008 KG v2 (flag-gated): when ``ctx.kg_v2_enabled`` and a graph DB exists, the
    KG subgraph is consulted FIRST and its nodes seed the envelope before any broad
    file read; with the flag off (default) the legacy executor path runs verbatim.
    """
    depth = lane_config(ctx.lane).context_depth
    cache_hit = False
    kg_consulted = False
    # FLOW-CONV semantic-cache: consult before re-retrieving (advisory, best-effort).
    if ctx.cache is not None and ctx.envelope is not None:
        cache_hit = True
        ctx.cache_hits += 1
        envelope = ctx.envelope
    else:
        kg_items = _kg_v2_seed_items(ctx) if ctx.kg_v2_enabled else None
        if kg_items:
            kg_consulted = True
            envelope = ContextEnvelope(
                task=ctx.task,
                items=kg_items,
                omissions=[],
                token_estimate=sum(i.tokens for i in kg_items),
            )
        elif ctx.context_engine_enabled:
            envelope = _context_engine_envelope(ctx, depth)
        else:
            envelope = ctx.executor.gather_context(ctx.task, ctx.seed_paths, depth)
            # Opportunistic KG grounding (C17+): when no seed paths were provided,
            # a KG index is available, and the kg_v2_enabled explicit-flag path did
            # not already attempt the KG, try seeding from the graph before falling
            # back to the task-statement placeholder. This ensures graph-indexed
            # projects always produce grounded envelopes without requiring flag changes.
            if not ctx.seed_paths and ctx.graph_db_path is not None and not ctx.kg_v2_enabled:
                _opp_items = _kg_v2_seed_items(ctx)
                if _opp_items:
                    kg_consulted = True
                    envelope = ContextEnvelope(
                        task=ctx.task,
                        items=_opp_items,
                        omissions=[],
                        token_estimate=sum(i.tokens for i in _opp_items),
                    )
    envelope = envelope.model_copy(update={"cache_hit": cache_hit})
    # Memory recall parity (SDD ExplorePhase): fold prior memory into the envelope.
    # A cached envelope was already folded + compressed on its original build, so
    # neither step re-runs on a cache hit.
    if not cache_hit:
        envelope = _fold_memory_recall(ctx, envelope)
        envelope, compression_evidence = _compress_envelope(ctx, envelope)
    else:
        compression_evidence = {
            "enabled": bool(ctx.compression_enabled),
            "applied": False,
            "reason": "cache hit; envelope reused verbatim",
        }
    # C17 (product-closure-r13): enrich envelope with receipt provenance fields so
    # context-envelope.json carries full auditability.  All fields are optional; this
    # is additive — callers that already set these values keep them unchanged.
    import hashlib
    import uuid as _uuid

    _budget_cap = OC_FLOW_BUDGETS["gather_context"][1]
    _ranking_hash = hashlib.sha1("|".join(i.ref for i in envelope.items).encode()).hexdigest()[:12]
    receipt_updates: dict[str, Any] = {}
    if not envelope.receipt_id:
        receipt_updates["receipt_id"] = str(_uuid.uuid4())
    if not envelope.ranking_hash:
        receipt_updates["ranking_hash"] = _ranking_hash
    if envelope.budget_used == 0:
        receipt_updates["budget_used"] = envelope.token_estimate
    if envelope.budget_available == 0:
        receipt_updates["budget_available"] = _budget_cap
    if not envelope.why_omitted:
        receipt_updates["why_omitted"] = list(envelope.omissions)
    # Set envelope confidence from KG item scores when KG was consulted and
    # envelope confidence has not been set by a caller.
    if kg_consulted and envelope.confidence == 0.0 and envelope.items:
        _mean_conf = sum(i.confidence for i in envelope.items) / len(envelope.items)
        if _mean_conf > 0.0:
            receipt_updates["confidence"] = _mean_conf
    if receipt_updates:
        envelope = envelope.model_copy(update=receipt_updates)
    ctx.envelope = envelope
    name = _write_json(ctx.artifacts_dir / "context-envelope.json", envelope.model_dump())
    # P1.2: persist context-receipt.json — a receipt view of the envelope that exposes
    # the key auditability fields next to context-envelope.json for easy discovery.
    # Laziest implementation: project the envelope's receipt fields into a flat dict.
    receipt_payload: dict[str, Any] = {
        "receipt_id": envelope.receipt_id,
        "items": [
            {
                "ref": i.ref,
                "why_included": i.why_included,
                "confidence": i.confidence,
            }
            for i in envelope.items
        ],
        "omissions": [{"why_omitted": o} for o in envelope.why_omitted],
        "budget": {
            "used": envelope.budget_used,
            "available": envelope.budget_available,
        },
        "ranking_hash": envelope.ranking_hash,
        "decision_dependency": envelope.decision_dependency,
        "confidence": envelope.confidence,
        # Compression evidence (context substrate parity): ratio, savings and the
        # honestly-skipped items are auditable next to the envelope items.
        "compression": compression_evidence,
    }
    receipt_name = _write_json(ctx.artifacts_dir / "context-receipt.json", receipt_payload)
    tokens = (
        0
        if cache_hit
        else min(
            envelope.token_estimate or _budget_for("gather_context"),
            OC_FLOW_BUDGETS["gather_context"][1],
        )
    )
    # RUN_STATE_CONTRACT needs_context producer: an envelope with ZERO items is
    # unusable for `plan` (ContextEnvelope.has_items) — the flow could not build
    # sufficient context for the task. The runner terminates such a run as
    # canonical ``needs_context`` instead of planning on nothing.
    outcome = NodeOutcome.OK
    if not envelope.has_items:
        outcome = NodeOutcome.NEEDS_CONTEXT
        if not ctx.block_reason:
            ctx.block_reason = (
                "insufficient context: gathering produced an empty context envelope "
                "for the task; index the project or pass seed paths and re-run"
            )
    return NodeResult(
        node="gather_context",
        outcome=outcome,
        outputs={
            "items": len(envelope.items),
            "omissions": len(envelope.omissions),
            "cache_hit": cache_hit,
            "kg_consulted": kg_consulted,
        },
        llm_tokens=tokens,
        artifacts=[name, receipt_name],
    )


def _context_engine_envelope(ctx: OCFlowContext, depth: int) -> ContextEnvelope:
    """PR-010 path: build the canonical envelope via the ContextEngine, then project.

    Flag-gated by ``ctx.context_engine_enabled``. Seeds the engine from KG v2 items
    (when available) or the seed paths, runs strategy -> budget -> pack -> envelope,
    and projects the canonical envelope onto the surgical OC Flow seam. Defensive:
    any failure falls back to the legacy executor gather so a run never breaks.
    """
    try:
        from opencontext_core.context.engine import ContextEngine, to_surgical_envelope
        from opencontext_core.models.context import ContextItem, ContextPriority

        kg_items = _kg_v2_seed_items(ctx) if ctx.kg_v2_enabled else None
        seeds = (
            [(i.ref, i.source, i.tokens) for i in kg_items]
            if kg_items
            else [(rel, "file", 200) for rel in list(ctx.seed_paths)[: max(1, depth) * 4]]
        )
        candidates = [
            ContextItem(
                id=ref,
                content=f"seed for: {ctx.task[:60]} ({ref})",
                source=ref,
                source_type=src_type,
                priority=ContextPriority.P2,
                tokens=tokens,
                score=0.6,
            )
            for ref, src_type, tokens in seeds
        ]
        result = ContextEngine().build(
            "oc_flow",
            "gather_context",
            ctx.task,
            candidates=candidates,
            l2={"task": ctx.task},
        )
        surgical = to_surgical_envelope(result.envelope)
        if not surgical.has_items:
            return ctx.executor.gather_context(ctx.task, ctx.seed_paths, depth)
        return surgical
    except Exception:  # pragma: no cover - defensive: never break a run on the v2 path
        return ctx.executor.gather_context(ctx.task, ctx.seed_paths, depth)


def _kg_v2_seed_items(ctx: OCFlowContext) -> list[ContextEnvelopeItem] | None:
    """KG-first envelope items from the v2 subgraph, or None to fall back to files.

    Best-effort and flag-gated: returns None when no graph DB is configured or the
    subgraph is empty, so ``node_gather_context`` falls back to the executor's
    file-based gather verbatim.
    """
    if ctx.graph_db_path is None:
        return None
    from opencontext_core.retrieval.kg_context import kg_first_subgraph

    subgraph = kg_first_subgraph(
        ctx.task,
        ctx.graph_db_path,
        workflow="oc-flow",
        node="gather_context",
        observer=ctx.kg_observer,
    )
    if subgraph is None or not subgraph.nodes:
        return None
    return [
        ContextEnvelopeItem(
            source="kg",
            ref=(n.path or n.name),
            summary=f"{n.type.value} {n.name}",
            tokens=80,
            why_included=f"kg:score={n.temporal.confidence:.2f}",
            confidence=n.temporal.confidence,
        )
        for n in subgraph.nodes
    ]


# Items whose carried content estimates below this are left uncompressed: shrinking
# an already-small summary would claim savings the envelope never actually spends.
_COMPRESSION_MIN_ITEM_TOKENS = 256

# Honest-skip reason for KG-sourced items (context substrate SQLite/JSON asymmetry):
# their summaries derive from the SQLite-backed graph, not a raw text payload, so
# compressing them would produce char-based token counts inconsistent with the
# graph-anchored estimate.
_KG_SQLITE_SKIP_REASON = (
    "sqlite-backed kg content; honest skip (token accounting stays graph-anchored)"
)


def _compress_envelope(
    ctx: OCFlowContext, envelope: ContextEnvelope
) -> tuple[ContextEnvelope, dict[str, Any]]:
    """Apply the CompressionEngine to oversized envelope content (substrate parity).

    Runs only when ``ctx.compression_enabled`` and the envelope exceeds the
    gather_context budget cap. KG-sourced items are honestly skipped (see
    :data:`_KG_SQLITE_SKIP_REASON`); compressed items re-anchor their token count
    to the char-based estimate of the compressed content. Returns the (possibly
    updated) envelope plus the evidence dict recorded in context-receipt.json.
    Best-effort: any engine failure leaves the envelope untouched with a reason.
    """
    if not ctx.compression_enabled:
        return envelope, {
            "enabled": False,
            "applied": False,
            "reason": "compression disabled (context.compression.enabled=false)",
        }
    budget_cap = OC_FLOW_BUDGETS["gather_context"][1]
    baseline = envelope.token_estimate
    if baseline <= budget_cap:
        return envelope, {
            "enabled": True,
            "applied": False,
            "reason": "envelope within gather budget; no compression needed",
            "baseline_tokens": baseline,
            "compressed_tokens": baseline,
            "ratio": 1.0,
            "skipped": [],
        }
    try:
        from opencontext_core.context.budgeting import estimate_tokens
        from opencontext_core.context.compression import CompressionEngine
        from opencontext_core.models.context import ContextItem, ContextPriority

        config = ctx.compression_config
        if config is None:
            from opencontext_core.config import CompressionConfig

            config = CompressionConfig()
        engine = CompressionEngine(config)
    except Exception as exc:  # compression is optional — never break the gather
        return envelope, {
            "enabled": True,
            "applied": False,
            "reason": f"compression engine unavailable: {type(exc).__name__}",
            "baseline_tokens": baseline,
            "compressed_tokens": baseline,
            "ratio": 1.0,
            "skipped": [],
        }
    skipped: list[dict[str, str]] = []
    new_items: list[ContextEnvelopeItem] = []
    compressed_any = False
    for item in envelope.items:
        if item.source == "kg":
            skipped.append({"ref": item.ref, "reason": _KG_SQLITE_SKIP_REASON})
            new_items.append(item)
            continue
        content = item.summary
        content_tokens = estimate_tokens(content)
        if content_tokens < _COMPRESSION_MIN_ITEM_TOKENS:
            new_items.append(item)
            continue
        try:
            result = engine.compress_item(
                ContextItem(
                    id=item.ref,
                    content=content,
                    source=item.ref,
                    source_type=item.source,
                    priority=ContextPriority.P2,
                    tokens=content_tokens,
                    score=item.confidence or 0.5,
                )
            )
        except Exception:
            new_items.append(item)
            continue
        if result.compressed_tokens >= content_tokens:
            new_items.append(item)  # engine kept it (protected spans / no gain)
            continue
        new_items.append(
            item.model_copy(
                update={"summary": result.item.content, "tokens": result.compressed_tokens}
            )
        )
        compressed_any = True
    total = sum(i.tokens for i in new_items)
    evidence: dict[str, Any] = {
        "enabled": True,
        "applied": compressed_any,
        "baseline_tokens": baseline,
        "compressed_tokens": total,
        "savings": max(0, baseline - total),
        "ratio": round(total / baseline, 4) if baseline else 1.0,
        "skipped": skipped,
    }
    if not compressed_any:
        evidence["reason"] = (
            "no compressible items (kg content honestly skipped)"
            if skipped
            else "no compressible items"
        )
        return envelope, evidence
    return envelope.model_copy(update={"items": new_items, "token_estimate": total}), evidence


# Omission notes recorded when memory recall cannot run (silent degrade, book §8).
_MEMORY_STORE_MISSING_NOTE = "memory enabled but no store resolvable; memory recall skipped"
_MEMORY_RECALL_FAILED_NOTE = "memory recall failed; envelope built without memory"

# How many memory records gather_context recalls (SDD ExplorePhase parity: limit=5).
_MEMORY_RECALL_LIMIT = 5

# Longest per-item summary carried into the envelope for a recalled memory record.
_MEMORY_SUMMARY_MAX_CHARS = 240


def _fold_memory_recall(ctx: OCFlowContext, envelope: ContextEnvelope) -> ContextEnvelope:
    """Fold prior memory recall into the envelope (SDD ExplorePhase parity).

    When memory is enabled and a store is resolvable, the task statement is
    searched and the top-scoring, non-episodic records join the envelope as
    ``source="memory"`` items — only while they fit the gather_context budget
    cap. A missing store or a failing search degrades to a recorded omission,
    never an error (memory is optional, it must not block a run).
    """
    if not ctx.memory_enabled:
        return envelope
    if ctx.memory_store is None:
        return envelope.model_copy(
            update={"omissions": [*envelope.omissions, _MEMORY_STORE_MISSING_NOTE]}
        )
    try:
        records = ctx.memory_store.search(ctx.task, limit=_MEMORY_RECALL_LIMIT)
    except Exception:
        return envelope.model_copy(
            update={"omissions": [*envelope.omissions, _MEMORY_RECALL_FAILED_NOTE]}
        )
    from opencontext_core.context.budgeting import estimate_tokens

    budget_cap = OC_FLOW_BUDGETS["gather_context"][1]
    candidates = sorted(
        (r for r in records or [] if str(getattr(r, "content", "") or "").strip()),
        key=lambda r: float(getattr(r, "confidence", 0.0) or 0.0),
        reverse=True,
    )
    items = list(envelope.items)
    total = envelope.token_estimate
    added = False
    for record in candidates:
        layer = getattr(record, "layer", None)
        if str(getattr(layer, "value", layer or "")) == "episodic":
            # Per-run breadcrumbs carry no actionable signal (ExplorePhase filter).
            continue
        content = str(record.content)
        tokens = estimate_tokens(content)
        if total + tokens > budget_cap:
            continue  # respect the existing envelope budget: never blow the cap
        confidence = min(max(float(getattr(record, "confidence", 0.0) or 0.0), 0.0), 1.0)
        record_ref = str(getattr(record, "key", "") or getattr(record, "id", "memory"))
        items.append(
            ContextEnvelopeItem(
                source="memory",
                ref=record_ref,
                summary=content[:_MEMORY_SUMMARY_MAX_CHARS],
                tokens=tokens,
                why_included=f"memory:score={confidence:.2f}",
                confidence=confidence,
            )
        )
        record_layer = getattr(record, "layer", None)
        ctx.memory_hits.append(
            {
                "id": record_ref,
                "type": str(getattr(record_layer, "value", record_layer) or "memory"),
                "score": confidence,
                "used_for": "context_pack",
            }
        )
        total += tokens
        added = True

    # Also fold in the user's CLI/MCP observations (memory_v2.db) so an
    # `opencontext memory v2 save` is visible to runs — the observations store and
    # the in-loop agent store (memory.db) were otherwise disjoint. Best-effort and
    # read-only: a missing/failing store is a silent no-op (memory never blocks a run).
    try:
        from pathlib import Path

        from opencontext_core.paths import StorageMode, resolve_storage_path

        obs_db = resolve_storage_path(Path(ctx.root), StorageMode.local) / "memory_v2.db"
        if obs_db.is_file():
            from opencontext_memory import MemoryStore, mem_search

            # Recall is associative, not exact: the store's FTS combines tokens
            # with implicit AND, so the full task rarely matches. Search per
            # salient token (len >= 4) and union the observations by id — any
            # token hit surfaces the observation.
            store = MemoryStore.open(obs_db)
            project = Path(ctx.root).name
            seen_obs: dict[str, dict[str, Any]] = {}
            task_tokens = {t.lower() for t in re.findall(r"[A-Za-z]{4,}", ctx.task)}
            for token in list(task_tokens)[:12]:
                for row in mem_search(
                    store, query=token, limit=_MEMORY_RECALL_LIMIT, project=project
                ):
                    rid = str(row.get("id") or row.get("topic_key") or row.get("title") or "")
                    if rid and rid not in seen_obs:
                        seen_obs[rid] = row
            for row in seen_obs.values():
                content = str(row.get("content") or row.get("title") or "").strip()
                if not content:
                    continue
                tokens = estimate_tokens(content)
                if total + tokens > budget_cap:
                    continue
                obs_ref = str(row.get("id") or row.get("topic_key") or "observation")
                items.append(
                    ContextEnvelopeItem(
                        source="memory",
                        ref=obs_ref,
                        summary=content[:_MEMORY_SUMMARY_MAX_CHARS],
                        tokens=tokens,
                        why_included="memory:observation",
                        confidence=0.5,
                    )
                )
                ctx.memory_hits.append(
                    {
                        "id": obs_ref,
                        "type": str(row.get("type") or "observation"),
                        "score": 0.5,
                        "used_for": "context_pack",
                    }
                )
                total += tokens
                added = True
    except Exception:
        pass

    if not added:
        return envelope
    return envelope.model_copy(update={"items": items, "token_estimate": total})


def node_plan(ctx: OCFlowContext) -> NodeResult:
    """Produce the frozen :class:`TaskContract` and persist it (book §9, FLOW-4)."""
    if ctx.envelope is None:
        raise OCFlowError("plan requires a context envelope")
    contract = ctx.executor.plan(ctx.task, ctx.envelope)
    ctx.contract = contract
    name = _write_json(ctx.artifacts_dir / "task-contract.json", contract.model_dump())
    return NodeResult(
        node="plan",
        outcome=NodeOutcome.OK,
        outputs={
            "acceptance_criteria": len(contract.acceptance_criteria),
            "changed_areas": list(contract.changed_areas),
        },
        llm_tokens=_budget_for("plan"),
        artifacts=[name],
    )


def node_mutate(ctx: OCFlowContext) -> NodeResult:
    """Apply surgical edits with reason+criterion, behind a rollback checkpoint
    (book §10, FLOW-7)."""
    if ctx.contract is None:
        raise OCFlowError("mutate requires a frozen task contract")
    edits = ctx.executor.mutate(ctx.contract, ctx.envelope or ContextEnvelope(task=ctx.task))
    # A productive executor records WHY it produced no usable edits (invalid edit
    # set / policy denial); surface it so the completion gate + CLI can report it.
    executor_block = getattr(ctx.executor, "block_reason", None)
    if executor_block and not edits:
        ctx.block_reason = executor_block
    # Policy-gate outcome (RUN_STATE_CONTRACT / DOC2 §10.4): thread the executor's
    # policy flags into the run context so the repair loop is forbidden and the
    # approval flavor surfaces as canonical ``needs_approval``.
    if bool(getattr(ctx.executor, "policy_blocked", False)):
        ctx.policy_blocked = True
    if bool(getattr(ctx.executor, "policy_approval_required", False)):
        ctx.policy_approval_required = True

    # Validate the surgical-mutation contract: every edit has a reason + criterion.
    for edit in edits:
        if not edit.reason:
            raise OCFlowError(f"edit for {edit.path} is missing a reason")
        if not (edit.requirement_refs or edit.task_refs):
            raise OCFlowError(f"edit for {edit.path} references no acceptance criterion")

    # RED-first (strict TDD ONLY): under a strict-TDD posture, the test must be
    # FAILING before we mutate — a "fix" applied to an already-green test would
    # otherwise report completed without having fixed anything. Gated on strict so
    # default ("ask"/"off") flows are byte-for-byte unchanged. Best-effort: a
    # test-runner error never blocks.
    if edits and ctx.tdd_mode == "strict" and ctx.test_command:
        _pre_exit: int | None = ctx.tdd_red_exit_code
        if _pre_exit is None:
            import os

            # Never write bytecode: the pre-check compiles the PRE-mutation (buggy)
            # source, and a same-second mutation would leave stale __pycache__ that the
            # post-mutation verify then reuses. Also add the root to PYTHONPATH so the
            # test imports the project's own modules.
            _red_env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
            _red_env["PYTHONDONTWRITEBYTECODE"] = "1"
            # AC-031: no .pytest_cache residue in the user's project tree.
            _red_env["PYTEST_ADDOPTS"] = "-p no:cacheprovider"
            _red_env["PYTHONPATH"] = str(ctx.root) + (
                os.pathsep + _red_env["PYTHONPATH"] if _red_env.get("PYTHONPATH") else ""
            )
            try:
                _pre = subprocess.run(
                    ctx.test_command,
                    cwd=ctx.root,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env=_red_env,
                )
            except (subprocess.SubprocessError, OSError):
                _pre = None
            _pre_exit = _pre.returncode if _pre is not None else None
        if _pre_exit == 0:
            ctx.block_reason = "RED-first: the test already passes — no failing test to fix"
            edits = []

    changed_paths = [(ctx.root / e.path).resolve() for e in edits]
    store = CheckpointStore(ctx.root)
    checkpoint = store.create(changed_paths, source="oc-flow-mutate") if changed_paths else None
    ctx.checkpoint_id = checkpoint.id if checkpoint is not None else "empty"
    ctx.checkpoint = checkpoint

    import hashlib

    # Pre-edit checksums per changed path (from the checkpoint's before-bytes) so
    # the receipt is a tamper-evident before→after record, not just a path list.
    _pre_ck: dict[Path, str] = {}
    if checkpoint is not None:
        for cf in checkpoint.files:
            if cf.existed and cf.blob:
                try:
                    _pre_ck[cf.path] = hashlib.sha256(
                        (checkpoint.dir / "files" / cf.blob).read_bytes()
                    ).hexdigest()
                except OSError:
                    pass

    receipts: list[dict[str, Any]] = []
    try:
        for edit in edits:
            applied = apply_edit(ctx.root, edit)
            rec = applied.model_dump()
            abs_path = (ctx.root / edit.path).resolve()
            rec["checksum_before"] = _pre_ck.get(abs_path)
            rec["checksum_after"] = (
                hashlib.sha256(abs_path.read_bytes()).hexdigest() if abs_path.is_file() else None
            )
            receipts.append(rec)
            if edit.path not in ctx.changed_files:
                ctx.changed_files.append(edit.path)
    except Exception as exc:
        if checkpoint is not None:
            checkpoint.restore()
            _write_json(
                ctx.artifacts_dir / "rollback-report.json",
                {"checkpoint_id": checkpoint.id, "reason": f"apply failed: {type(exc).__name__}"},
            )
        ctx.block_reason = f"apply failed: {type(exc).__name__}"
        raise

    # C10 (product-closure-r13): build a real unified diff from checkpoint before-bytes
    # and current (post-edit) file bytes. OQ-1 resolved: CheckpointStore.create captures
    # pre-edit bytes in checkpoint.dir/"files"/{index}.blob for every changed path.
    patch_parts: list[str] = []
    if edits and checkpoint is not None:
        snap_by_path = {f.path: f for f in checkpoint.files}
        for edit in edits:
            abs_path = (ctx.root / edit.path).resolve()
            snap = snap_by_path.get(abs_path)
            if snap and snap.existed and snap.blob:
                before_bytes = (checkpoint.dir / "files" / snap.blob).read_bytes()
                before_lines = before_bytes.decode("utf-8", errors="replace").splitlines(
                    keepends=True
                )
            else:
                before_lines = []
            after_lines = (
                abs_path.read_bytes().decode("utf-8", errors="replace").splitlines(keepends=True)
                if abs_path.exists()
                else []
            )
            diff = list(
                difflib.unified_diff(
                    before_lines,
                    after_lines,
                    fromfile=f"a/{edit.path}",
                    tofile=f"b/{edit.path}",
                )
            )
            patch_parts.extend(diff)
    if not patch_parts:
        patch_parts = ["# no edits proposed (honest no-op mutation)\n"]
    patch_name = ctx.artifacts_dir / "patch.diff"
    patch_name.parent.mkdir(parents=True, exist_ok=True)
    # Write as bytes: unified-diff line endings must be preserved exactly so
    # ``git apply --check`` works on Windows where text-mode write_text would
    # double-CR the CRLF lines already present in the diff payload.
    # Normalise CRLF → LF so the patch stays portable across platforms
    # (works against either LF or CRLF working trees after git checkout).
    patch_text = "".join(patch_parts).replace("\r\n", "\n").replace("\r", "\n")
    patch_name.write_bytes(patch_text.encode("utf-8", errors="replace"))
    rec_name = _write_json(
        ctx.artifacts_dir / "apply-receipts.json",
        {"checkpoint_id": ctx.checkpoint_id, "receipts": receipts},
    )
    return NodeResult(
        node="mutate",
        outcome=NodeOutcome.OK,
        outputs={
            "edits": len(edits),
            "checkpoint_id": ctx.checkpoint_id,
            "changed_files": list(ctx.changed_files),
        },
        llm_tokens=_budget_for("mutate"),
        artifacts=["patch.diff", rec_name],
    )


def node_local_inspection(ctx: OCFlowContext) -> NodeResult:
    """Run the zero-LLM local inspection and map to a typed outcome (book §11)."""
    report = run_local_inspection(
        ctx.root,
        ctx.changed_files,
        test_command=ctx.test_command,
        lint_command=ctx.lint_command,
        typecheck_command=ctx.typecheck_command,
        run_external=ctx.run_external_inspection,
        mutation_required=ctx.mutation_required,
    )
    ctx.inspection = report
    name = _write_json(ctx.artifacts_dir / "inspection-report.json", report.model_dump())
    rollback_name = None
    if report.outcome == "failed_blocking" and ctx.checkpoint is not None:
        ctx.checkpoint.restore()
        rollback_name = _write_json(
            ctx.artifacts_dir / "rollback-report.json",
            {
                "checkpoint_id": ctx.checkpoint.id,
                "reason": report.failure_summary or "blocking inspection failure",
                "restored_files": list(ctx.changed_files),
            },
        )
    outcome_map = {
        "passed": NodeOutcome.PASSED,
        "failed_recoverable": NodeOutcome.FAILED_RECOVERABLE,
        "failed_blocking": NodeOutcome.FAILED_BLOCKING,
        "skipped_with_reason": NodeOutcome.PASSED,  # no skip edge — proceed (book §6)
    }
    return NodeResult(
        node="local_inspection",
        outcome=outcome_map[report.outcome],
        outputs={"outcome": report.outcome, "gates": len(report.gate_results)},
        llm_tokens=0,
        artifacts=[a for a in [name, rollback_name] if a],
    )


def _repair_forbidden(ctx: OCFlowContext) -> tuple[NodeOutcome, str, str] | None:
    """DOC2 §10.4 ``forbidden_when`` guard for the diagnosis/repair loop.

    Returns ``(outcome, condition, reason)`` when the loop must NOT run at all:

    * ``policy_blocked`` — the policy gate already blocked this run; repairing
      around a policy refusal is never allowed.
    * ``tdd_red_not_proven`` — a strict mutation run without proven RED evidence
      (no red run, or an already-green one) has nothing legitimate to repair.
    * ``missing_executor`` — a mutation run that produced no edits with no
      productive executor: retrying diagnosis can never yield an applicable fix.

    Returns ``None`` when repair is allowed (e.g. recoverable verification/lint
    failure on a mutated run — the ``allowed_when`` cases).
    """
    if ctx.policy_blocked:
        return (
            NodeOutcome.POLICY_BLOCKED,
            "policy_blocked",
            "repair loop forbidden: the policy gate already blocked this run",
        )
    red_proven = ctx.tdd_red_exit_code is not None and ctx.tdd_red_exit_code != 0
    if ctx.tdd_mode == "strict" and ctx.mutation_required and not red_proven:
        return (
            NodeOutcome.ATTEMPTS_EXHAUSTED,
            "tdd_red_not_proven",
            "repair loop forbidden: strict TDD test-first (RED) evidence is absent",
        )
    if (
        ctx.mutation_required
        and not ctx.changed_files
        and not bool(getattr(ctx.executor, "provider_available", False))
    ):
        return (
            NodeOutcome.ATTEMPTS_EXHAUSTED,
            "missing_executor",
            "repair loop forbidden: no productive executor is available to apply a fix",
        )
    return None


def node_diagnose(ctx: OCFlowContext) -> NodeResult:
    """Bounded, evidence-driven diagnosis loop (book §12, FLOW-5, FLOW-6).

    DOC2 §10.4: the loop is bounded by ``ctx.max_attempts`` and refuses to run at
    all under the :func:`_repair_forbidden` conditions — recording ZERO attempts.
    """
    forbidden = _repair_forbidden(ctx)
    if forbidden is not None:
        outcome, condition, reason = forbidden
        if not ctx.block_reason:
            ctx.block_reason = reason
        return NodeResult(
            node="diagnose",
            outcome=outcome,
            outputs={"attempts": 0, "forbidden": condition, "reason": reason},
            llm_tokens=0,
        )
    if len(ctx.diagnosis_attempts) >= ctx.max_attempts:
        return NodeResult(
            node="diagnose",
            outcome=NodeOutcome.ATTEMPTS_EXHAUSTED,
            outputs={"attempts": len(ctx.diagnosis_attempts), "max_attempts": ctx.max_attempts},
            llm_tokens=0,
        )
    if ctx.contract is None or ctx.inspection is None:
        raise OCFlowError("diagnose requires a contract and a failed inspection")

    attempt_no = len(ctx.diagnosis_attempts) + 1
    attempt = ctx.executor.diagnose(attempt_no, ctx.contract, ctx.inspection, ctx.failed_strategies)
    # Never repeat a failed strategy (book §12).
    if attempt.fix_strategy in ctx.failed_strategies:
        return NodeResult(
            node="diagnose",
            outcome=NodeOutcome.ATTEMPTS_EXHAUSTED,
            outputs={"reason": "no untried strategy remains"},
            llm_tokens=0,
        )
    ctx.diagnosis_attempts.append(attempt)
    ctx.failed_strategies.append(attempt.fix_strategy)
    name = _write_json(
        ctx.artifacts_dir / "diagnosis" / f"attempt-{attempt_no:03d}.json",
        attempt.model_dump(),
    )
    return NodeResult(
        node="diagnose",
        outcome=NodeOutcome.FIX_READY,
        outputs={
            "attempt": attempt_no,
            "selected": attempt.selected_hypothesis,
            "fix_strategy": attempt.fix_strategy,
        },
        llm_tokens=_budget_for("diagnose"),
        artifacts=[name],
    )


def node_escalation(ctx: OCFlowContext) -> NodeResult:
    """Produce a human handoff; never mutate code (book §13, FLOW-13)."""
    blocking = (
        ctx.inspection.failure_summary
        if ctx.inspection is not None
        else "could not converge within OC Flow bounds"
    ) or "blocked"
    report = EscalationReport(
        blocking_error=blocking,
        owner_candidates=_owner_candidates(ctx.root, ctx.changed_files),
        known_blockers=[a.fix_strategy for a in ctx.diagnosis_attempts],
        next_recommended_action="escalate to SDD or a human owner for a deeper fix",
        failed_strategies=list(ctx.failed_strategies),
    )
    rep_name = _write_json(
        ctx.artifacts_dir / "escalation" / "escalation-report.json", report.model_dump()
    )
    handoff = (
        f"# OC Flow Handoff\n\n"
        f"**Task:** {ctx.task}\n\n"
        f"**Blocking error:** {report.blocking_error}\n\n"
        f"**Owner candidates:** {', '.join(report.owner_candidates)}\n\n"
        f"**Attempts made:** {len(ctx.diagnosis_attempts)}\n\n"
        f"**Strategies ruled out:** {', '.join(report.failed_strategies) or 'none'}\n\n"
        f"**Next action:** {report.next_recommended_action}\n"
    )
    handoff_path = ctx.artifacts_dir / "escalation" / "handoff.md"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(handoff, encoding="utf-8")
    return NodeResult(
        node="escalation",
        outcome=NodeOutcome.OK,
        outputs={"owner_candidates": report.owner_candidates},
        llm_tokens=_budget_for("escalation"),
        artifacts=[rep_name, "escalation/handoff.md"],
    )


def _persist_memory_delta(ctx: OCFlowContext, memory_delta: dict[str, Any]) -> dict[str, Any]:
    """Persist the run's memory delta via the harvester/harness (ArchivePhase parity).

    Durable memory writes MUST route through ``MemoryHarvester`` — and through the
    ``MemoryHarness`` sole writer when ``memory_v2_enabled`` — exactly like the SDD
    ArchivePhase; this function never calls ``store.write`` directly (AVH-002).
    Returns a harvest outcome dict recorded inside memory-delta.json: either
    ``persisted: True`` with run provenance (``run_id``, ``origin="agent"``) or an
    honest no-op with a reason. Best-effort: a failing harvest never blocks the run.
    """
    if not ctx.memory_enabled:
        return {"persisted": False, "reason": "memory disabled (memory.enabled=false)"}
    if ctx.memory_store is None:
        return {"persisted": False, "reason": "no memory store resolvable for project root"}
    if not ctx.memory_harvest_enabled:
        return {"persisted": False, "reason": "harvest disabled (memory.harvest_after_run=false)"}
    try:
        from types import SimpleNamespace

        from opencontext_core.memory.harvester import MemoryHarvester

        harness = None
        if ctx.memory_v2_enabled:
            from opencontext_core.memory.harness import MemoryHarness

            harness = MemoryHarness(ctx.memory_store)
        run_id = ctx.run_id or "unknown"
        # Duck-typed run result matching what the SDD ArchivePhase feeds the
        # harvester (task/run_id/status + empty gate/ledger evidence for OC Flow).
        run_result = SimpleNamespace(
            run_id=run_id,
            task=ctx.task,
            status=ctx.inspection.outcome if ctx.inspection else "not_run",
            gates=[],
            ledgers=[],
            artifacts=[],
            context_omitted_paths=[],
        )
        harvester = MemoryHarvester(ctx.memory_store, harness=harness)
        records = harvester.harvest(run_result)
        outcome: dict[str, Any] = {
            "persisted": True,
            "run_id": run_id,
            "origin": "agent",
            "harvested_records": len(records),
            "via": "harness" if harness is not None else "harvester-legacy",
        }
        # MEMORY_CONTRACT rule 4: the run report counts every candidate this
        # run produced (harvested records + promoted durable notes below).
        ctx.memory_new_candidates = len(records)
        durable_notes = memory_delta.get("durable_notes") or []
        if durable_notes:
            if harness is not None:
                outcome["promoted_notes"] = _promote_durable_notes(harness, durable_notes, run_id)
                ctx.memory_new_candidates += int(outcome["promoted_notes"])
            else:
                # Honest skip: without the harness sole writer there is no
                # sanctioned promotion path for free-form notes from here.
                outcome["durable_notes_skipped_reason"] = (
                    "memory_v2 disabled; durable notes remain in memory-delta.json only"
                )
        return outcome
    except Exception as exc:  # memory is optional — never block consolidation
        return {"persisted": False, "reason": f"harvest failed: {type(exc).__name__}"}


def _promote_durable_notes(harness: Any, durable_notes: list[str], run_id: str) -> int:
    """Promote consolidation durable notes through the sole-writer harness.

    Each note becomes a :class:`MemoryCandidate` with run provenance
    (``run:{run_id}`` evidence + ``origin="agent"`` metadata) and runs the full
    8-step promotion lifecycle; rejected candidates are counted out honestly.
    """
    from opencontext_core.memory_usability.memory_candidates import (
        MemoryCandidate,
        MemoryKind,
    )
    from opencontext_core.models.context import DataClassification
    from opencontext_core.models.evidence import EvidenceRef

    promoted = 0
    for note in durable_notes:
        candidate = MemoryCandidate(
            content=str(note),
            source=f"run:{run_id}",
            kind=MemoryKind.FACT,  # harness re-classifies from content
            novelty_score=0.6,
            reuse_likelihood=0.7,
            classification=DataClassification.INTERNAL,
            token_cost=max(1, len(str(note)) // 4),
            source_trust=0.7,
            proposed_by="oc-flow-consolidation",
            evidence_refs=[
                EvidenceRef(
                    source=f"run:{run_id}",
                    source_type="run",
                    confidence=0.7,
                    run_id=run_id,
                )
            ],
            expected_reuse="bias future oc-flow runs of similar tasks",
            confidence=0.7,
            metadata={"origin": "agent", "run_id": run_id},
        )
        receipt = harness.promote(candidate)
        if getattr(receipt, "action", "reject") != "reject":
            promoted += 1
    return promoted


def node_consolidation(ctx: OCFlowContext) -> NodeResult:
    """Finalize: deltas, summary, reindex, cost report (book §14, FLOW-14)."""
    # C11 (product-closure-r13): gate durable_notes behind PromotionPolicyV2.
    # Composite score derived from run signals: inspection outcome + changed-file count.
    # A generic no-op run scores 0.0 → REJECT (below keep threshold 0.6).
    from opencontext_core.memory.v2.promotion import (
        PromotionPolicyV2,
        PromotionVerdictV2,
        evaluate_promotion,
    )

    score = 0.0
    if ctx.inspection and ctx.inspection.outcome in ("ok", "passed"):
        score += 0.3
    score += min(len(ctx.changed_files), 5) * 0.1
    score = min(score, 1.0)

    verdict = evaluate_promotion(score, PromotionPolicyV2())

    memory_delta: dict[str, Any] = {
        "task": ctx.task,
        "failed_strategies": list(ctx.failed_strategies),
        "saved_chain_of_thought": False,  # book §14: never save CoT
    }
    if verdict == PromotionVerdictV2.PROMOTE:
        memory_delta["durable_notes"] = [f"OC Flow change: {ctx.task[:160]}"]
    else:
        memory_delta["promotion"] = "not_promoted"
    graph_delta = {
        "reindexed_files": list(ctx.changed_files),
        "changed_areas": list(ctx.contract.changed_areas) if ctx.contract else [],
    }
    cost_report = {
        "diagnosis_attempts": len(ctx.diagnosis_attempts),
        "cache_hits": ctx.cache_hits,
        "changed_files": len(ctx.changed_files),
    }
    # Persist the memory delta through the harvester/harness sole-writer path
    # (SDD ArchivePhase parity). The outcome — persisted or an honest no-op with
    # a reason — is recorded inside memory-delta.json (the run's evidence).
    harvest_outcome = _persist_memory_delta(ctx, memory_delta)
    memory_delta["harvest"] = harvest_outcome
    mem_name = _write_json(ctx.artifacts_dir / "consolidation" / "memory-delta.json", memory_delta)
    graph_name = _write_json(ctx.artifacts_dir / "consolidation" / "graph-delta.json", graph_delta)
    summary = (
        f"# OC Flow Summary\n\n"
        f"Task: {ctx.task}\n\n"
        f"Changed files: {', '.join(ctx.changed_files) or 'none'}\n\n"
        f"Diagnosis attempts: {len(ctx.diagnosis_attempts)}\n\n"
        f"Cache hits: {ctx.cache_hits}\n"
    )
    summary_path = ctx.artifacts_dir / "consolidation" / "summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary, encoding="utf-8")
    # C13 (product-closure-r13): stable alias at the artifacts root for easy discovery.
    alias_path = ctx.artifacts_dir / "run-summary.md"
    alias_path.write_text(summary, encoding="utf-8")
    _write_json(ctx.artifacts_dir / "consolidation" / "cost-report.json", cost_report)
    return NodeResult(
        node="consolidation",
        outcome=NodeOutcome.OK,
        # C16 (product-closure-r13): expose promotion_verdict so runner.py can emit
        # a typed memory_promotion RuntimeDecision without re-importing promotion here.
        outputs={
            "reindexed": list(ctx.changed_files),
            "cost": cost_report,
            "promotion_verdict": verdict.value,
            "memory_persisted": bool(harvest_outcome.get("persisted", False)),
        },
        llm_tokens=_budget_for("consolidation"),
        artifacts=[mem_name, graph_name, "consolidation/summary.md"],
    )


# Node dispatch table.
NODE_HANDLERS: dict[str, Any] = {
    "init": node_init,
    "gather_context": node_gather_context,
    "plan": node_plan,
    "mutate": node_mutate,
    "local_inspection": node_local_inspection,
    "diagnose": node_diagnose,
    "escalation": node_escalation,
    "consolidation": node_consolidation,
}


# --------------------------------------------------------------- exit-condition guards
def can_exit_init(ctx: OCFlowContext) -> bool:
    """Book §7: session + definition + config snapshot + capabilities + policy known."""
    return ctx.init_done and (ctx.artifacts_dir / "init.json").exists()


def can_exit_gather_context(ctx: OCFlowContext) -> bool:
    """Book §8: a context envelope must exist before planning (FLOW-3)."""
    return ctx.envelope is not None


def can_exit_plan(ctx: OCFlowContext) -> bool:
    """Book §9: a frozen contract with criteria + verification must exist."""
    return (
        ctx.contract is not None
        and bool(ctx.contract.acceptance_criteria)
        and bool(ctx.contract.verification_plan)
    )


def can_exit_mutate(ctx: OCFlowContext) -> bool:
    """Book §10: receipts + patch + rollback checkpoint must exist."""
    return (
        ctx.checkpoint_id is not None
        and (ctx.artifacts_dir / "patch.diff").exists()
        and (ctx.artifacts_dir / "apply-receipts.json").exists()
    )


EXIT_GUARDS: dict[str, Any] = {
    "init": can_exit_init,
    "gather_context": can_exit_gather_context,
    "plan": can_exit_plan,
    "mutate": can_exit_mutate,
}


def can_exit(node: str, ctx: OCFlowContext) -> bool:
    """Return whether ``node``'s exit conditions are satisfied (default: True)."""
    guard = EXIT_GUARDS.get(node)
    return guard(ctx) if guard is not None else True


def make_apply_edit(
    path: str,
    *,
    content: str,
    operation: ApplyOperation = ApplyOperation.CREATE_FILE,
    reason: str,
    requirement_ref: str,
    start_line: int | None = None,
    end_line: int | None = None,
    after_line: int | None = None,
) -> ApplyEdit:
    """Convenience builder for a contract-bearing :class:`ApplyEdit` (tests/CLI)."""
    return ApplyEdit(
        path=path,
        operation=operation,
        content=content,
        reason=reason,
        requirement_refs=[requirement_ref],
        start_line=start_line,
        end_line=end_line,
        after_line=after_line,
    )
