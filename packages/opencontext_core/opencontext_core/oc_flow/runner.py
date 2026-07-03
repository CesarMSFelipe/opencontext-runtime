"""OCFlowRunner — drives OC Flow under Runtime governance (PR-007, FLOW-1, FLOW-2,
FLOW-3, FLOW-15, FLOW-16, FLOW-CONV §6).

The runner walks the declarative graph from ``start_node``, dispatches each node
handler, enforces the per-node exit conditions and token budgets, resolves the next
node from the typed outcome, and persists artifacts/events/decision receipts under
the run's artifact tree. It consults an advisory Runtime Brain (PR-000.1) for the
next-node recommendation — advisory only; the deterministic graph governs (doc 59
§Brain restrictions). It also resolves ``--workflow auto`` to OC Flow for localized
tasks and recommends escalation to SDD as risk/scope grows.

Layering (doc 58): L9 composing L1 ids, L2 stores, L8 brain (via port), L6 registries
— all downward.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opencontext_core.agents.executor import ApplyEdit
from opencontext_core.context.planning.workflow_selector import (
    WorkflowSelection,
)
from opencontext_core.context.planning.workflow_selector import (
    select_workflow as _shared_select_workflow,
)
from opencontext_core.oc_flow.budgets import (
    BudgetGuard,
    resolve_max_attempts,
)
from opencontext_core.oc_flow.completion import (
    CompletionStatus,
    completion_reason,
    mutation_required,
    resolve_completion,
    verification_required,
)
from opencontext_core.oc_flow.definition import oc_flow_definition, resolve_next_node
from opencontext_core.oc_flow.models import (
    DiagnosisAttempt,
    InspectionReport,
    Lane,
    NodeOutcome,
    TaskContract,
)
from opencontext_core.oc_flow.nodes import (
    NODE_HANDLERS,
    DeterministicNodeExecutor,
    NodeExecutor,
    OCFlowContext,
    OCFlowError,
    can_exit,
)
from opencontext_core.oc_flow.personas import persona_id_for_oc_flow_node
from opencontext_core.paths import StorageMode, resolve_storage_path, resolve_workspace_path
from opencontext_core.runtime.brain import NullRuntimeBrain, RuntimeBrainPort
from opencontext_core.runtime.decisions import (
    DecisionLog,
    RuntimeDecision,
    summarize_decision_log,
)
from opencontext_core.runtime.ids import new_run_id, new_session_id

# Safety cap on total node steps (the diagnosis attempt budget already bounds the
# loop; this guards against any pathological graph cycle).
_MAX_STEPS = 50

# Event family per node event (doc 59 §Event hierarchy).
_NODE_EVENT_FAMILY = "workflow"


@dataclass
class OCFlowRunResult:
    """The outcome of an OC Flow run."""

    run_id: str
    session_id: str
    # completed | blocked | needs_executor | needs_provider | needs_user_edit | escalated
    status: str
    final_node: str
    visited: list[str] = field(default_factory=list)
    artifacts_dir: Path | None = None
    total_tokens: int = 0
    diagnosis_attempts: int = 0
    escalated: bool = False
    decisions: list[dict[str, Any]] = field(default_factory=list)
    # B1 / AVH-011: the honest terminal status, why, and the workflow-selection
    # receipt (B6). ``graph_status`` keeps the raw traversal verdict for tooling.
    graph_status: str = "completed"
    completion_reason: str = ""
    mutation_required: bool = False
    workflow_selection: dict[str, Any] = field(default_factory=dict)
    verified_by: list[str] = field(default_factory=list)
    verification_outcome: str = "not_run"


# --------------------------------------------------------------------- workflow selector
def select_workflow(task: str) -> str:
    """Resolve ``--workflow auto`` to ``oc-flow`` or ``sdd`` (FLOW-CONV, B6).

    Delegates to the ONE shared selector (``context.planning.workflow_selector``) so
    ``run --workflow auto`` and ``simulate`` cannot disagree (AVH-013). No routing
    policy lives here any more.
    """
    return _shared_select_workflow(task).workflow


def should_escalate_to_sdd(contract: TaskContract, *, max_changed_areas: int = 5) -> bool:
    """Recommend switching to SDD when scope/risk outgrows OC Flow (book §23)."""
    if len(contract.changed_areas) > max_changed_areas:
        return True
    risk = {r.lower() for r in contract.risk_flags}
    high_risk = {"public_api", "schema", "architecture", "security", "migration", "breaking_change"}
    return bool(risk & high_risk)


def _discover_test_command(root: Path) -> list[str] | None:
    """Small pytest discovery for test-fix tasks."""
    tests = sorted(
        p.relative_to(root)
        for pattern in ("test_*.py", "*_test.py")
        for p in root.rglob(pattern)
        if ".opencontext" not in p.parts
    )
    if not tests:
        return None
    # NOTE: caps at 10 to avoid running the full suite; pass explicit test_command for large repos.
    return [sys.executable, "-m", "pytest", "-q", *[str(p) for p in tests[:10]]]


# ------------------------------------------------------------------------------- runner
class OCFlowRunner:
    """Executes the OC Flow workflow definition under Runtime governance."""

    def __init__(
        self,
        root: Path,
        *,
        executor: NodeExecutor | None = None,
        brain: RuntimeBrainPort | None = None,
        cache: Any | None = None,
        enabled: bool = True,
        context_engine_enabled: bool | None = None,
        kg_v2_enabled: bool | None = None,
        memory_store: Any | None = None,
    ) -> None:
        self.root = Path(root)
        self.definition = oc_flow_definition()
        self.executor = executor or DeterministicNodeExecutor()
        # Advisory-only Brain (flag-gated): defaults to the inert NullRuntimeBrain.
        self.brain: RuntimeBrainPort = brain or NullRuntimeBrain()
        self.brain_advisory = brain is not None
        self.cache = cache
        self.enabled = enabled
        # VDM-004 seam wiring: resolve the PR-010 ContextEngine (context_engine) and
        # PR-008 KG v2 (kg_v2) gather-path flags. An explicit ctor value wins (cli /
        # tests); otherwise they come from the project config at ``root`` so flipping
        # ``runtime.context_engine_enabled`` / ``runtime.kg_v2_enabled`` activates the
        # vNext gather path with no code change. Default config = legacy (both off).
        if context_engine_enabled is None or kg_v2_enabled is None:
            runtime_cfg = self._load_runtime_config()
            if context_engine_enabled is None:
                context_engine_enabled = bool(getattr(runtime_cfg, "context_engine_enabled", False))
            if kg_v2_enabled is None:
                kg_v2_enabled = bool(getattr(runtime_cfg, "kg_v2_enabled", False))
        self._context_engine_enabled = bool(context_engine_enabled)
        self._kg_v2_enabled = bool(kg_v2_enabled)
        # Always locate the KG index regardless of the kg_v2_enabled flag. When the
        # index is present and no seed paths are given, node_gather_context uses the
        # path for opportunistic KG grounding even without kg_v2_enabled=True. On an
        # unindexed project _resolve_graph_db_path() returns None so no seeding occurs.
        self._graph_db_path = self._resolve_graph_db_path()
        # Memory + compression parity (SDD harness/context substrate): resolve the
        # agent memory store and the compression config from the project config so
        # gather_context reads memory / compresses oversized content and
        # consolidation persists the memory delta through the harvester/harness.
        # An injected store (tests/hosts) wins over config resolution.
        self._memory_enabled = False
        self._memory_harvest_enabled = False
        self._memory_v2_enabled = False
        self._memory_store: Any | None = memory_store
        self._compression_enabled = False
        self._compression_config: Any | None = None
        self._resolve_memory_and_compression()

    # -- config / kg resolution ----------------------------------------------
    def _load_runtime_config(self) -> Any:
        """Load the project's RuntimeMigration flags from ``<root>/opencontext.yaml``.

        Config is advisory here: a missing or invalid config yields built-in defaults
        (every migration flag legacy-off via ``getattr(..., False)``), so flag-off
        behaviour is byte-identical to before this seam was wired.
        """
        try:
            from opencontext_core.config import load_config_or_defaults
            from opencontext_core.config_resolver import resolve_config_path

            config = load_config_or_defaults(resolve_config_path(self.root), auto_detect=False)
            return config.runtime
        except Exception:  # pragma: no cover - config is advisory; default to legacy.
            return None

    def _resolve_memory_and_compression(self) -> None:
        """Resolve memory flags/store + compression config from the project config.

        Mirrors the SDD harness runner: the store MUST resolve to the same DB
        (path + provider) the runtime's recall path reads, so it comes from
        ``BackendFactory.create_memory_store`` honoring ``memory.provider`` and the
        storage mode. Best-effort: any failure degrades to no-memory /
        no-compression and the nodes record the omission or no-op reason honestly.
        """
        try:
            from opencontext_core.config import load_config_or_defaults
            from opencontext_core.config_resolver import resolve_config_path

            config = load_config_or_defaults(resolve_config_path(self.root), auto_detect=False)
        except Exception:  # config is advisory; run without memory/compression
            return
        memory_cfg = getattr(config, "memory", None)
        self._memory_enabled = bool(getattr(memory_cfg, "enabled", False))
        self._memory_harvest_enabled = bool(getattr(memory_cfg, "harvest_after_run", False))
        self._memory_v2_enabled = bool(
            getattr(getattr(config, "runtime", None), "memory_v2_enabled", False)
        )
        compression_cfg = getattr(getattr(config, "context", None), "compression", None)
        self._compression_enabled = bool(getattr(compression_cfg, "enabled", False))
        self._compression_config = compression_cfg
        if self._memory_store is None and self._memory_enabled:
            try:
                from opencontext_core.backends.factory import BackendFactory

                storage_path = resolve_storage_path(
                    self.root,
                    config.storage.mode,
                    getattr(config.storage, "custom_path", None),
                )
                storage_path.mkdir(parents=True, exist_ok=True)
                self._memory_store = BackendFactory.create_memory_store(config, storage_path)
            except Exception:  # store is optional — gather/consolidation degrade
                self._memory_store = None

    def _resolve_graph_db_path(self) -> Path | None:
        """Locate the project's KG v2 index under ``root``, or None when unindexed.

        ``kg_first_subgraph`` returns None for a missing DB, so kg_v2 stays active but
        non-fatal on an unindexed project (the gather falls back to the legacy path).
        """
        from opencontext_core.config_resolver import resolve_active_storage_file

        for name in ("context_graph.db", "codegraph.db"):
            candidate = resolve_active_storage_file(self.root, name)
            if candidate.exists():
                return candidate
        return None

    # -- paths ----------------------------------------------------------------
    def _run_dir(self, session_id: str, run_id: str) -> Path:
        return (
            resolve_workspace_path(self.root, StorageMode.local)
            / "sessions"
            / session_id
            / "runs"
            / run_id
        )

    def _artifacts_dir(self, session_id: str, run_id: str) -> Path:
        return self._run_dir(session_id, run_id) / "artifacts" / "oc-flow"

    # -- run ------------------------------------------------------------------
    def run(
        self,
        task: str,
        *,
        lane: Lane | str = Lane.FAST,
        profile: str | None = "balanced",
        seed_paths: list[str] | None = None,
        requested_edits: list[ApplyEdit] | None = None,
        run_external_inspection: bool = False,
        test_command: list[str] | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> OCFlowRunResult:
        """Run OC Flow end to end for ``task`` (FLOW-16, book §25)."""
        if not self.enabled:
            raise OCFlowError("OC Flow is disabled (set runtime.oc_flow_enabled=true)")

        lane_enum = Lane(str(lane))
        session_id = session_id or new_session_id()
        run_id = run_id or new_run_id()
        artifacts_dir = self._artifacts_dir(session_id, run_id)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # If a caller passed concrete edits, drive them through the deterministic
        # executor so a model-free run can still apply a real surgical change.
        executor = self.executor
        if requested_edits is not None and isinstance(executor, DeterministicNodeExecutor):
            executor = DeterministicNodeExecutor(requested_edits=requested_edits)

        # B1 / AVH-011: classify whether this task implies a mutation; threaded into
        # the inspection scope gate and the post-graph completion gate.
        mut_required = mutation_required(task)
        verify_required = verification_required(task)
        if verify_required and test_command is None:
            test_command = _discover_test_command(self.root)
        run_external_inspection = run_external_inspection or bool(test_command)
        # C16: compute once, use for both ctx and the retry_policy decision below.
        _max_attempts_resolved = resolve_max_attempts(profile=profile, lane=lane_enum)
        ctx = OCFlowContext(
            root=self.root,
            artifacts_dir=artifacts_dir,
            task=task,
            lane=lane_enum,
            profile=profile,
            executor=executor,
            max_attempts=_max_attempts_resolved,
            seed_paths=seed_paths or [],
            cache=self.cache,
            run_external_inspection=run_external_inspection,
            test_command=test_command,
            mutation_required=mut_required,
            # VDM-004: vNext gather-path flags reach the node handlers here. With both
            # off (default config) node_gather_context runs the legacy executor path.
            context_engine_enabled=self._context_engine_enabled,
            kg_v2_enabled=self._kg_v2_enabled,
            graph_db_path=self._graph_db_path,
            # Memory + compression parity: gather_context folds memory recall and
            # compresses oversized content; consolidation persists the memory delta
            # through the harvester/harness with this run's provenance.
            memory_enabled=self._memory_enabled,
            memory_store=self._memory_store,
            memory_harvest_enabled=self._memory_harvest_enabled,
            memory_v2_enabled=self._memory_v2_enabled,
            run_id=run_id,
            compression_enabled=self._compression_enabled,
            compression_config=self._compression_config,
        )

        # B6 / AVH-013: the explainable workflow-selection receipt (same shared
        # selector `run --workflow auto` and `simulate` consume).
        selection = _shared_select_workflow(task)

        decisions = DecisionLog()
        events: list[dict[str, Any]] = []
        guard = BudgetGuard()
        visited: list[str] = []

        node = self.definition.start_node
        status = "completed"
        steps = 0
        self._emit_event(
            events,
            "workflow.selected",
            node,
            {
                "workflow": "oc-flow",
                "lane": lane_enum.value,
                "selection_reason": selection.reason,
                "selection_signals": selection.signals,
                "mutation_required": mut_required,
            },
        )

        # C16 (product-closure-r13): emit RuntimeDecision records for the real
        # selection points made by this run.  Only record decisions for selection
        # points that ACTUALLY EXIST in OC Flow today (book §Brain restrictions):
        #   workflow, context_strategy, provider, execution_profile, retry_policy.
        #   NOT emitted (no real selection): persona (deterministic lookup),
        #   skill_bundle (not in OC Flow runner today).
        decisions.append(
            RuntimeDecision(
                kind="workflow",
                chosen=selection.workflow,
                reason=selection.reason,
                alternatives=["sdd"] if selection.workflow == "oc-flow" else ["oc-flow"],
                confidence=0.9,
                inputs={"signals": list(selection.signals), "lane": lane_enum.value},
            )
        )
        _context_strategy = (
            "context_engine"
            if self._context_engine_enabled
            else ("kg_v2" if self._kg_v2_enabled else "legacy")
        )
        decisions.append(
            RuntimeDecision(
                kind="context_strategy",
                chosen=_context_strategy,
                reason=(
                    "context_engine_enabled flag"
                    if self._context_engine_enabled
                    else ("kg_v2_enabled flag" if self._kg_v2_enabled else "default legacy gather")
                ),
                alternatives=(
                    ["kg_v2", "legacy"]
                    if self._context_engine_enabled
                    else (
                        ["context_engine", "legacy"]
                        if self._kg_v2_enabled
                        else ["context_engine", "kg_v2"]
                    )
                ),
                confidence=1.0,
                inputs={
                    "context_engine_enabled": self._context_engine_enabled,
                    "kg_v2_enabled": self._kg_v2_enabled,
                },
            )
        )
        _provider_chosen = (
            "deterministic" if not bool(getattr(executor, "provider_available", False)) else "model"
        )
        decisions.append(
            RuntimeDecision(
                kind="provider",
                chosen=_provider_chosen,
                reason=(
                    "no model provider configured; deterministic executor active"
                    if _provider_chosen == "deterministic"
                    else "model provider available"
                ),
                alternatives=(
                    ["model"] if _provider_chosen == "deterministic" else ["deterministic"]
                ),
                confidence=1.0,
                inputs={"provider_available": _provider_chosen != "deterministic"},
            )
        )
        decisions.append(
            RuntimeDecision(
                kind="execution_profile",
                chosen=profile or "balanced",
                reason=f"profile='{profile or 'balanced'}' passed by caller",
                confidence=1.0,
                inputs={"lane": lane_enum.value},
            )
        )
        decisions.append(
            RuntimeDecision(
                kind="retry_policy",
                chosen=str(_max_attempts_resolved),
                reason=(
                    f"resolve_max_attempts(profile={profile!r}, lane={lane_enum.value!r})"
                    f" → {_max_attempts_resolved}"
                ),
                confidence=1.0,
                inputs={
                    "profile": profile,
                    "lane": lane_enum.value,
                    "max_attempts": _max_attempts_resolved,
                },
            )
        )

        while node not in self.definition.terminal_nodes:
            steps += 1
            if steps > _MAX_STEPS:
                status = "failed"
                break
            handler = NODE_HANDLERS.get(node)
            if handler is None:
                raise OCFlowError(f"no handler for node {node!r}")

            self._emit_event(events, "node.started", node, {})
            result = handler(ctx)
            visited.append(node)
            guard.charge(node, result.llm_tokens)
            self._emit_event(
                events,
                "node.completed",
                node,
                {"outcome": result.outcome.value, "tokens": result.llm_tokens},
            )

            # C16: after consolidation, emit the memory_promotion decision so
            # decisions.json captures the PromotionPolicyV2 verdict.
            if node == "consolidation":
                verdict_str = str(result.outputs.get("promotion_verdict", "not_promoted"))
                decisions.append(
                    RuntimeDecision(
                        kind="memory_promotion",
                        chosen=verdict_str,
                        reason=(
                            "PromotionPolicyV2 evaluated composite score from run signals "
                            "(inspection outcome + changed-file count)"
                        ),
                        confidence=0.8,
                        inputs={
                            "changed_files": len(ctx.changed_files),
                            "inspection_outcome": (
                                ctx.inspection.outcome if ctx.inspection else "not_run"
                            ),
                        },
                    )
                )

            # Exit-condition guard (book §7-§11): refuse to advance until met.
            if not can_exit(node, ctx):
                raise OCFlowError(f"exit conditions not satisfied for node {node!r}")

            target = self._next_node(node, result.outcome, ctx, decisions, guard, events)
            if target is None:
                status = "failed"
                break
            if target == "escalation":
                status = "escalated"
            node = target

        # Terminal handling. The graph reaching its `completed` node is NOT proof a
        # mutation task was done — the completion gate (B1/ADR-A1) maps the raw graph
        # verdict onto an honest status; a no-op mutation can never report `completed`.
        final_node = node
        graph_status = status
        provider_available = bool(getattr(executor, "provider_available", False))
        completion = resolve_completion(
            graph_status,
            ctx,
            mutation_required=mut_required,
            provider_available=provider_available,
            verification_required=verify_required,
        )
        status = completion.value
        reason = (
            ctx.block_reason
            if completion is not CompletionStatus.completed and ctx.block_reason
            else completion_reason(completion, mutation_required=mut_required)
        )

        # R4: post-run confidence report — emit as a RuntimeDecision so
        # decisions.json captures the ConfidenceEngine evaluation.  Real signals
        # come from the completed run context; absent signals fall back to the
        # conservative default (ConfidenceSignals default = None → disclosed).
        try:
            from opencontext_core.runtime_intelligence.confidence import (
                ConfidenceEngine,
                ConfidenceSignals,
            )

            _inspection = ctx.inspection
            _signals = ConfidenceSignals(
                inspection_confidence=(
                    1.0
                    if (_inspection and _inspection.outcome == "passed")
                    else 0.0
                    if _inspection is not None
                    else None
                ),
            )
            _cr = ConfidenceEngine().report(
                session_id=session_id,
                run_id=run_id,
                workflow="oc-flow",
                signals=_signals,
            )
            decisions.append(
                RuntimeDecision(
                    kind="confidence_report",
                    chosen=str(round(_cr.overall, 4)),
                    reason=(
                        f"ConfidenceEngine post-run report: overall={_cr.overall:.4f}, "
                        f"action={_cr.recommended_action}"
                    ),
                    confidence=_cr.overall,
                    inputs=dict(_cr.dimensions),
                )
            )
        except Exception:
            pass  # confidence emission is advisory; never interrupts the run

        self._persist(
            session_id,
            run_id,
            ctx,
            events,
            decisions,
            guard,
            status,
            visited,
            graph_status=graph_status,
            completion_reason=reason,
            mutation_required=mut_required,
            selection=selection,
        )

        return OCFlowRunResult(
            run_id=run_id,
            session_id=session_id,
            status=status,
            final_node=final_node,
            visited=visited,
            artifacts_dir=artifacts_dir,
            total_tokens=guard.total,
            diagnosis_attempts=len(ctx.diagnosis_attempts),
            escalated=("escalation" in visited),
            decisions=summarize_decision_log(decisions),
            graph_status=graph_status,
            completion_reason=reason,
            mutation_required=mut_required,
            verified_by=list(ctx.inspection.verified_by) if ctx.inspection else [],
            verification_outcome=(
                ctx.inspection.verification_outcome if ctx.inspection else "not_run"
            ),
            workflow_selection={
                "workflow": selection.workflow,
                "reason": selection.reason,
                "signals": selection.signals,
            },
        )

    # -- transition + decision receipt ---------------------------------------
    def _next_node(
        self,
        node: str,
        outcome: NodeOutcome,
        ctx: OCFlowContext,
        decisions: DecisionLog,
        guard: BudgetGuard,
        events: list[dict[str, Any]],
    ) -> str | None:
        """Resolve the next node from the graph, recording a decision receipt.

        The advisory Brain may recommend; the deterministic graph governs (the
        recommendation is recorded in the decision inputs, never enforced).
        """
        target = resolve_next_node(self.definition, node, outcome)

        brain_reco: str | None = None
        if self.brain_advisory:
            recommendation = self.brain.recommend(
                run_id=None,
                runtime_context={
                    "current_node": node,
                    "proposed_node": target,
                    "task": ctx.task,
                    "outcome": outcome.value,
                },
            )
            if recommendation is not None:
                brain_reco = recommendation.chosen

        if target is None:
            return None

        persona = persona_id_for_oc_flow_node(target)
        node_budget = guard.per_node.get(node, 0)
        decision = RuntimeDecision(
            kind="next_node",
            chosen=target,
            reason=(
                f"graph routes '{node}' (outcome={outcome.value}) to '{target}'"
                + (f"; brain recommended '{brain_reco}'" if brain_reco else "")
            ),
            alternatives=[
                e.to_node
                for e in self.definition.edges
                if e.from_node == node and e.to_node != target
            ],
            confidence=0.9,
            governed_by="state_machine",  # the SM governs; Brain only advises.
            inputs={
                "triggering_outcome": outcome.value,
                "lane": ctx.lane.value,
                "persona": persona,
                "budget_tokens": node_budget,
                "brain_recommendation": brain_reco,
            },
            node_id=node,
        )
        decisions.append(decision)
        self._emit_event(
            events, "decision.recorded", node, {"chosen": target, "outcome": outcome.value}
        )
        return target

    # -- events / persistence -------------------------------------------------
    def _emit_event(
        self, events: list[dict[str, Any]], event_type: str, node: str, data: dict[str, Any]
    ) -> None:
        events.append(
            {
                "type": event_type,
                "family": _NODE_EVENT_FAMILY,
                "node": node,
                "ts": datetime.now(tz=UTC).isoformat(),
                "data": data,
            }
        )

    def _persist(
        self,
        session_id: str,
        run_id: str,
        ctx: OCFlowContext,
        events: list[dict[str, Any]],
        decisions: DecisionLog,
        guard: BudgetGuard,
        status: str,
        visited: list[str],
        *,
        graph_status: str = "completed",
        completion_reason: str = "",
        mutation_required: bool = False,
        selection: WorkflowSelection | None = None,
    ) -> None:
        run_dir = self._run_dir(session_id, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "schema_version": "opencontext.oc_flow.run_state.v1",
            "run_id": run_id,
            "session_id": session_id,
            "workflow": "oc-flow",
            "task": ctx.task,
            "lane": ctx.lane.value,
            "profile": ctx.profile,
            "status": status,
            "graph_status": graph_status,
            "completion_reason": completion_reason,
            "mutation_required": mutation_required,
            "verified_by": list(ctx.inspection.verified_by) if ctx.inspection else [],
            "verification_outcome": (
                ctx.inspection.verification_outcome if ctx.inspection else "not_run"
            ),
            "workflow_selection": (
                {
                    "workflow": selection.workflow,
                    "reason": selection.reason,
                    "signals": selection.signals,
                }
                if selection is not None
                else {}
            ),
            "visited": visited,
            "changed_files": list(ctx.changed_files),
            "checkpoint_id": ctx.checkpoint_id,
            "max_attempts": ctx.max_attempts,
            "diagnosis_attempts": len(ctx.diagnosis_attempts),
            "total_tokens": guard.total,
            "budget_violations": [v.model_dump() for v in guard.violations],
        }
        _dump(run_dir / "state.json", state)
        _dump(run_dir / "events.json", {"events": events})
        _dump(run_dir / "decisions.json", {"decisions": summarize_decision_log(decisions)})

    # -- resume ---------------------------------------------------------------
    def resume(self, session_id: str, run_id: str) -> ResumedRun:
        """Restore OC Flow state from persisted artifacts, or fail safe (FLOW-15).

        Restores the task contract, context envelope, patch state, receipts,
        inspection report and diagnosis attempts. If a required artifact (the task
        contract) is missing, resume fails without executing any further node.
        """
        run_dir = self._run_dir(session_id, run_id)
        artifacts_dir = self._artifacts_dir(session_id, run_id)
        if not run_dir.is_dir():
            raise OCFlowError(f"no run to resume: {session_id}/{run_id}")

        contract_path = artifacts_dir / "task-contract.json"
        if not contract_path.is_file():
            raise OCFlowError("cannot resume: required artifact task-contract.json is missing")
        contract = TaskContract.model_validate(_load(contract_path))

        envelope = None
        env_path = artifacts_dir / "context-envelope.json"
        if env_path.is_file():
            from opencontext_core.oc_flow.models import ContextEnvelope

            envelope = ContextEnvelope.model_validate(_load(env_path))

        receipts = _load(artifacts_dir / "apply-receipts.json") or {}
        patch = ""
        patch_path = artifacts_dir / "patch.diff"
        if patch_path.is_file():
            patch = patch_path.read_text(encoding="utf-8")

        inspection = None
        insp_path = artifacts_dir / "inspection-report.json"
        if insp_path.is_file():
            inspection = InspectionReport.model_validate(_load(insp_path))

        attempts: list[DiagnosisAttempt] = []
        diag_dir = artifacts_dir / "diagnosis"
        if diag_dir.is_dir():
            for attempt_file in sorted(diag_dir.glob("attempt-*.json")):
                attempts.append(DiagnosisAttempt.model_validate(_load(attempt_file)))

        state = _load(run_dir / "state.json") or {}
        return ResumedRun(
            session_id=session_id,
            run_id=run_id,
            contract=contract,
            envelope=envelope,
            patch=patch,
            apply_receipts=receipts,
            inspection=inspection,
            diagnosis_attempts=attempts,
            state=state,
        )


@dataclass
class ResumedRun:
    """Fully restored OC Flow state (FLOW-15, book §22)."""

    session_id: str
    run_id: str
    contract: TaskContract
    envelope: Any | None
    patch: str
    apply_receipts: dict[str, Any]
    inspection: InspectionReport | None
    diagnosis_attempts: list[DiagnosisAttempt]
    state: dict[str, Any]


def _dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _load(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
