"""HarnessRunner — orchestrates workflow execution with phase governance."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, ClassVar

from opencontext_core.agents.sdd_orchestrator import (
    PHASE_DEPENDENCIES,
    WORKFLOW_TRACKS,
)
from opencontext_core.harness.budget import TokenBudgetEnforcer
from opencontext_core.harness.config import HarnessConfig
from opencontext_core.harness.gates import (
    ApprovalRequiredForWritesGate,
    ConfidenceGate,
    FailingTestExistsGate,
    IncludedSourcesPresentGate,
    NoHighRiskExportsGate,
    NoSecretLeakageGate,
    OmissionsRecordedGate,
    PrivacyGate,
    ProviderPolicyPassedGate,
    ReviewArtifactCreatedGate,
    SecurityScanPassedGate,
    TraceIdCreatedGate,
)
from opencontext_core.harness.models import (
    BudgetMode,
    GateStatus,
    HarnessArtifact,
    HarnessDecision,
    HarnessRunResult,
    PhaseGate,
    PhaseLedger,
    PrivacyProfile,
    PrivacyRule,
)
from opencontext_core.harness.phases import (
    ApplyPhase,
    ArchivePhase,
    DesignPhase,
    ExplorePhase,
    GGARulesPhase,
    HarnessPhase,
    JudgmentDayPhase,
    PhaseResult,
    ProposePhase,
    ReviewPhase,
    SpecPhase,
    TasksPhase,
    VerifyPhase,
)
from opencontext_core.models.trace import RunEvent

_log = logging.getLogger(__name__)


class HarnessState:
    """Mutable state accumulated during a harness run."""

    def __init__(self, run_id: str, root: Path, task: str = "", max_tokens: int = 6000) -> None:
        self.run_id = run_id
        self.root = root
        self.task = task
        self.max_tokens = max_tokens
        self.ledgers: list[PhaseLedger] = []
        self.gates: list[PhaseGate] = []
        self.artifacts: list[HarnessArtifact] = []
        self.decisions: list[HarnessDecision] = []
        self.trace_ids: list[str] = []
        self.warnings: list[str] = []
        # Verified context pack rendered by the explore phase, fed to later phases'
        # executor prompts so the model works from retrieved evidence.
        self.context_pack: str = ""
        # Concrete file edits produced by the executor for ApplyPhase to write.
        # List of {"path": ..., "content": ...} dicts (or FileEdit instances).
        self.apply_edits: list[Any] = []
        # Phases for which human approval has been granted (e.g. {"apply"}).
        self.approved_phases: set[str] = set()
        # Executor/delegation layer the work-producing phases (spec/design/tasks)
        # run via run_phase_executor. None when no real LLM is configured, in
        # which case those phases report honest planned/executor-absent results.
        self.delegate: Any = None
        # Context provenance recorded by ExplorePhase, consumed by the propose
        # phase's provenance gates (included_sources_present / omissions_recorded).
        self.context_sources: set[str] = set()
        self.context_required_sources: list[str] = []
        self.context_omitted: int = 0
        self.context_omissions_recorded: int = 0


class HarnessRunner:
    """Orchestrates workflow execution with phase governance.

    Runs SDD phases (explore → propose → apply → verify → review → archive)
    with token budget enforcement, gates, and artifact persistence.
    """

    def __init__(
        self,
        root: Path,
        config: HarnessConfig | None = None,
        *,
        llm_gateway: Any = None,
    ) -> None:
        self.root = root.resolve()
        self.config = config or HarnessConfig.from_yaml_file(root / ".opencontext" / "harness.yaml")
        self.enforcer = TokenBudgetEnforcer()
        # Optional explicit LLM gateway. When provided (and not the mock
        # provider) the runner builds a live executor from it and attaches it to
        # the run state so spec/design/tasks produce real artifacts. When absent
        # the runner resolves a gateway from the configured provider, falling
        # back to no executor (honest planned/executor-absent) for mock/local.
        self._llm_gateway = llm_gateway

        # Agent memory store. This MUST resolve to the same DB (path + provider)
        # the runtime's recall path reads, or every harvested memory lands in a
        # store recall never opens (write-only memory). The runtime recalls from
        # .storage/opencontext honoring memory.provider; resolve the same way
        # here from the project config instead of a hardcoded-local store under
        # .opencontext.
        try:
            from opencontext_core.backends.factory import BackendFactory
            from opencontext_core.config import load_config_or_defaults

            oc_config = load_config_or_defaults(self.root / "opencontext.yaml")
            storage_path = self.root / ".storage" / "opencontext"
            storage_path.mkdir(parents=True, exist_ok=True)
            self._memory_store = BackendFactory.create_memory_store(oc_config, storage_path)
        except Exception:
            from opencontext_core.memory.agent import NullAgentMemoryStore

            self._memory_store = NullAgentMemoryStore()

    def create_run(self, workflow: str, task: str) -> HarnessState:
        """Create a new run with a unique run_id.

        Attaches a live executor to ``state.delegate`` when a real (non-mock)
        LLM gateway is configured, so the work-producing phases run it. When no
        real model is available the attribute is left unset and those phases keep
        their honest planned/executor-absent behavior.
        """
        run_id = f"{workflow}-{uuid.uuid4().hex[:12]}"
        state = HarnessState(
            run_id=run_id,
            root=self.root,
            task=task,
            max_tokens=6000,
        )
        delegate = self._build_executor()
        if delegate is not None:
            state.delegate = delegate
        return state

    def _build_executor(self) -> Any:
        """Build the work-producing-phase executor from the configured gateway.

        Resolves a gateway and its provider/model, then builds a delegation
        layer that runs spec/design/tasks through it. Returns ``None`` when no
        real model is available (mock/local default, or gateway construction
        failed) so the harness stays honest instead of faking success.
        """
        try:
            from opencontext_core.agents.executor import build_phase_executor

            gateway, provider, model = self._resolve_gateway()
            return build_phase_executor(
                gateway, provider=provider, model=model, phase_models=self._phase_model_map()
            )
        except Exception:
            # Executor wiring is opt-in/best-effort: never break a run because a
            # gateway could not be constructed. Phases fall back to honest
            # planned/executor-absent reporting.
            return None

    def _generate_apply_edits(self, state: HarnessState) -> list[Any]:
        """Produce concrete file edits for the apply phase via the live gateway.

        Returns ``[]`` (apply stays planned) when no real model resolves or the
        model returns nothing parseable. Never raises — codegen failure degrades
        to planned, it does not break the run.
        """
        try:
            from opencontext_core.agents.executor import generate_apply_edits

            gateway, provider, model = self._resolve_gateway()
            if gateway is None or provider == "mock":
                return []
            context = {"task": state.task, "context": state.context_pack}
            return list(generate_apply_edits(gateway, context, provider=provider, model=model))
        except Exception as exc:
            state.warnings.append(f"apply: codegen failed, planned only: {exc}")
            return []

    def _phase_model_map(self) -> dict[str, str]:
        """Per-phase model overrides from the active SDD profile (empty if none).

        Reads the profile name from this run root's SDD context, looks up the
        profile's per-phase model assignments, and drops ``default`` sentinels so
        only real overrides reach the executor. Best-effort: any failure yields no
        overrides, leaving every phase on the configured default model.
        """
        phase_map: dict[str, str] = {}
        try:
            import json

            context = self.root / ".opencontext" / "sdd" / "context.json"
            name = (
                json.loads(context.read_text(encoding="utf-8")).get("sdd_model_profile")
                if context.exists()
                else None
            )
            if name:
                from opencontext_core.sdd_profiles import SDDProfileManager

                profile = SDDProfileManager().get_profile(name)
                if profile is not None:
                    phase_map = {
                        phase: model
                        for phase, model in profile.model_assignments.items()
                        if model and model != "default"
                    }
        except Exception:
            phase_map = {}

        # Overlay per-persona model overrides (a persona override wins over the
        # phase's profile model) — e.g. Orchestrator=opus, Explorer=sonnet.
        try:
            from opencontext_core.config import load_config_or_defaults
            from opencontext_core.personas import PHASE_PERSONAS

            cfg = load_config_or_defaults(self.root / "opencontext.yaml", auto_detect=False)
            persona_models = getattr(cfg.sdd, "persona_models", {}) or {}
            for phase, persona_id in PHASE_PERSONAS.items():
                model = persona_models.get(persona_id)
                if model and model != "default":
                    phase_map[phase] = model
            # Explicit per-phase overrides in models.phases win (top-level config).
            # Previously these were read into state.current_phase_model and never
            # applied — so per-phase routing was dead. Route them through here.
            for phase, model_cfg in (getattr(cfg.models, "phases", {}) or {}).items():
                model = getattr(model_cfg, "model", None)
                if model and model != "default":
                    phase_map[phase] = model
        except Exception:
            pass
        return phase_map

    def _resolve_gateway(self) -> tuple[Any, str, str]:
        """Resolve (gateway, provider, model) for the work-producing executor.

        An explicitly injected gateway takes priority: it is an explicit intent
        to use a real executor, so it is paired with a non-mock provider label
        regardless of config. Otherwise the default provider is read from this
        run root's ``opencontext.yaml``; for ``mock`` (the zero-config default)
        the gateway is ``None`` so no executor is attached. For a real provider
        the runtime's gateway construction is used.
        """
        from opencontext_core.config import load_config_or_defaults

        # Scope resolution to this run's root — do not walk up to an unrelated
        # parent project's config (keeps wiring deterministic per run root).
        cfg = load_config_or_defaults(self.root / "opencontext.yaml", auto_detect=False)
        default = cfg.models.default
        provider = getattr(default, "provider", "mock")
        model = getattr(default, "model", "")

        if self._llm_gateway is not None:
            # An injected gateway overrides a mock config so the executor runs.
            effective_provider = provider if provider != "mock" else "injected"
            return self._llm_gateway, effective_provider, model

        # Prefer the host agent's selected model (MCP sampling) when available —
        # this is the zero-config path, so it overrides even a mock provider.
        from opencontext_core.config import SecurityMode

        if cfg.security.mode is not SecurityMode.AIR_GAPPED:
            from opencontext_core.llm.sampling_gateway import SamplingGateway, get_host_sampler

            sampler = get_host_sampler()
            if sampler is not None:
                return SamplingGateway(sampler, model=model), "host", model

        if provider == "mock":
            return None, provider, model

        # Real provider configured but no gateway injected: ask the runtime to
        # build one from config. If it cannot, fall back to no executor.
        try:
            from opencontext_core.runtime import OpenContextRuntime

            runtime = OpenContextRuntime(
                config=cfg,
                storage_path=self.root / ".storage" / "opencontext",
            )
            return runtime.llm_gateway, provider, model
        except Exception:
            return None, provider, model

    # ------------------------------------------------------------------
    # Phase scheduling — the single live spine.
    #
    # Folded from SDDOrchestrator: phase ordering, track selection and
    # dependency resolution now live here and drive HarnessRunner.run, replacing
    # the previous hardcoded ``phase_ids`` list. SDDOrchestrator's
    # PHASE_DEPENDENCIES / WORKFLOW_TRACKS remain the shared DAG declaration.
    # ------------------------------------------------------------------

    # Maps a runner ``workflow`` name to a declared WORKFLOW_TRACKS track.
    _WORKFLOW_TRACK_ALIASES: ClassVar[dict[str, str]] = {
        "sdd": "full",
        "full": "full",
        "standard": "standard",
        "quick": "quick",
        "full+judgment": "full+judgment",
        "full+gga": "full+gga",
        "full+quality": "full+quality",
    }

    @staticmethod
    def resolve_dag(phases: list[str], deps: dict[str, list[str]]) -> list[str]:
        """Topologically order ``phases`` by ``deps`` (Kahn's algorithm).

        Only in-set dependencies are considered. A phase whose dependencies
        cannot all be satisfied within ``phases`` (e.g. a dep absent from the
        set, or a cycle) is dropped rather than run out of order. Ordering is
        deterministic: ready phases are emitted in their declared ``phases``
        order.
        """
        phase_set = set(phases)
        # In-set dependency map.
        in_deps: dict[str, set[str]] = {
            p: {d for d in deps.get(p, []) if d in phase_set} for p in phases
        }
        ordered: list[str] = []
        completed: set[str] = set()
        # Iterate to a fixpoint, emitting newly-ready phases in declared order.
        progressed = True
        while progressed:
            progressed = False
            for p in phases:
                if p in completed:
                    continue
                if in_deps[p] <= completed:
                    ordered.append(p)
                    completed.add(p)
                    progressed = True
        # Anything still unresolved had an unsatisfiable dependency → drop it.
        return ordered

    def schedule_phases(self, workflow: str) -> list[str]:
        """Resolve the phase execution order for ``workflow`` via the DAG.

        Track selection: known track aliases (``sdd``→full, ``standard``,
        ``quick``) use that track's declared phases + deps. Custom runner
        workflows (``explore-only``, ``apply-only``, and the default) select a
        phase subset and resolve it through the shared PHASE_DEPENDENCIES DAG.
        """
        track_name = self._WORKFLOW_TRACK_ALIASES.get(workflow)
        if track_name is not None:
            track = WORKFLOW_TRACKS[track_name]
            phases = track["phases"]
            deps = track["deps"]
            assert isinstance(phases, list)
            assert isinstance(deps, dict)
            return self.resolve_dag(list(phases), dict(deps))

        # Custom workflows: pick a subset, resolve via the canonical DAG.
        if workflow == "explore-only":
            subset = ["explore"]
        elif workflow == "apply-only":
            subset = ["apply", "verify", "archive"]
        else:
            subset = ["explore", "archive"]

        # Restrict PHASE_DEPENDENCIES to the subset so ordering stays DAG-driven.
        # ``apply-only`` intentionally omits apply's upstream deps; dropping
        # out-of-subset deps keeps the requested phases runnable while
        # resolve_dag still enforces the in-subset ordering.
        deps_subset = {p: [d for d in PHASE_DEPENDENCIES.get(p, []) if d in subset] for p in subset}
        return self.resolve_dag(subset, deps_subset)

    def run(
        self,
        workflow: str,
        task: str,
        budget_mode: BudgetMode = BudgetMode.WARN,
        *,
        apply_edits: list[Any] | None = None,
        approved_phases: set[str] | None = None,
    ) -> HarnessRunResult:
        """Execute a full workflow with all phases.

        Args:
            workflow: Workflow name (sdd / explore-only / apply-only / ...).
            task: Task / change name.
            budget_mode: Token budget enforcement mode.
            apply_edits: Concrete file edits the executor produced, handed to
                ApplyPhase. Each item is a ``{"path", "content"}`` dict.
            approved_phases: Phases for which human approval has been granted.
                Used by the ``approval_required_for_writes`` pre-gate.
        """
        state = self.create_run(workflow, task)
        if apply_edits:
            state.apply_edits = list(apply_edits)
        state.approved_phases = set(approved_phases or set())
        results: list[PhaseResult] = []
        # Append-only typed event ledger: one immutable action/observation record
        # per executed phase (and per phase blocked before execution), so a run
        # can be inspected and replayed deterministically.
        events: list[RunEvent] = []
        final_status = GateStatus.PASSED
        # A hard failure (e.g. an apply pre-gate blocking a write) must not be
        # downgraded to WARNING by subsequent non-strict phase outcomes.
        hard_failed = False

        # Warn if knowledge graph has not been indexed (ExplorePhase depends on it)
        self._warn_if_kg_not_indexed(state)

        # Single spine: resolve the phases to run through the folded DAG/track
        # scheduler (PHASE_DEPENDENCIES / WORKFLOW_TRACKS), not a hardcoded list.
        phase_ids = self.schedule_phases(workflow)

        for phase_id in phase_ids:
            # Evaluate ConfidenceGate before running the phase
            phase_config = self.config.phases.get(phase_id)
            if phase_config is not None and phase_config.confidence_threshold is not None:
                prev_gates = state.gates if state.gates else None
                confidence_gate = ConfidenceGate().evaluate(
                    phase=phase_id,
                    threshold=phase_config.confidence_threshold,
                    previous_gates=prev_gates,
                    complexity_override=phase_config.complexity,
                )
                if confidence_gate.status == GateStatus.FAILED:
                    state.gates.append(confidence_gate)
                    state.warnings.append(
                        f"{phase_id}: confidence gate blocked "
                        f"(score below {phase_config.confidence_threshold})"
                    )
                    if budget_mode is BudgetMode.STRICT:
                        final_status = GateStatus.FAILED
                        break
                    # In non-strict modes, still warn but continue
                    continue

            # PrivacyGate: evaluate privacy rules when a privacy profile is active (opt-in)
            # Privacy is independent of budget_mode — activated via privacy_profile config
            if self.config.privacy_profile is not PrivacyProfile.OFF:
                privacy_rules = self._load_privacy_rules()
                if privacy_rules:
                    run_dir = state.root / ".opencontext" / "runs" / state.run_id
                    for rule in privacy_rules:
                        privacy_gate = PrivacyGate()
                        # Operation is determined by phase type
                        operation = self._operation_for_phase(phase_id)
                        gate_result = privacy_gate.evaluate(operation, rule, run_dir=run_dir)
                        if gate_result.status == GateStatus.FAILED:
                            state.gates.append(gate_result)
                            state.warnings.append(f"{phase_id}: privacy rule violated: {rule.name}")
                            final_status = GateStatus.FAILED
                            break
                    if final_status == GateStatus.FAILED:
                        break

            # Apply PRE-gates: human-approval + TDD failing-test ordering MUST be
            # evaluated and able to BLOCK before ApplyPhase touches any file.
            if phase_id == "apply":
                pre_gates, blocked = self._evaluate_apply_pre_gates(state, phase_config)
                state.gates.extend(pre_gates)
                if blocked:
                    blocking = [g.id for g in pre_gates if g.status == GateStatus.FAILED]
                    for gate_id in blocking:
                        state.warnings.append(f"apply: blocked by pre-gate '{gate_id}'")
                    events.append(
                        RunEvent(
                            index=len(events),
                            phase="apply",
                            action="blocked_pre_gate",
                            inputs_summary=self._inputs_summary(state),
                            status=GateStatus.FAILED.value,
                            observation=(
                                f"apply blocked before write by pre-gate(s): {', '.join(blocking)}"
                            ),
                            metadata={"blocking_gates": blocking},
                        )
                    )
                    final_status = GateStatus.FAILED
                    hard_failed = True
                    # Do NOT build/run ApplyPhase — no filesystem mutation occurs.
                    continue

            # Apply codegen: when a real executor is wired (host model / provider)
            # and no edits were supplied by a caller, ask the model to produce the
            # concrete file edits so ApplyPhase writes real source instead of a
            # scaffold. forbidden_paths + rollback in ApplyPhase guard the write.
            if phase_id == "apply" and not state.apply_edits and state.delegate is not None:
                state.apply_edits = self._generate_apply_edits(state)

            phase_obj = self._build_phase(phase_id, budget_mode)
            if phase_obj is None:
                continue

            try:
                result = phase_obj.run(state)
            except Exception as exc:
                result = PhaseResult(
                    phase=phase_id,
                    status=GateStatus.FAILED,
                    gates=[
                        PhaseGate(
                            id=f"{phase_id}_error",
                            phase=phase_id,
                            status=GateStatus.FAILED,
                            message=f"Phase error: {exc}",
                        )
                    ],
                )
                state.warnings.append(f"{phase_id}: {exc}")

            results.append(result)
            state.ledgers.extend([result.ledger] if result.ledger else [])
            state.gates.extend(result.gates)
            state.artifacts.extend(result.artifacts)
            state.decisions.extend(result.decisions)

            if result.trace_id:
                state.trace_ids.append(result.trace_id)

            # Config-driven gate dispatch: run the per-phase declared gates that
            # the phase itself did not already emit (e.g. security_scan_passed,
            # no_high_risk_exports, provider_policy_passed).
            dispatched = self._dispatch_declared_gates(state, phase_id, phase_config, result)
            state.gates.extend(dispatched)
            if any(g.status == GateStatus.FAILED for g in dispatched):
                if budget_mode is BudgetMode.STRICT:
                    final_status = GateStatus.FAILED
                elif not hard_failed:
                    final_status = GateStatus.WARNING

            # Record one typed event for this executed phase (action + observation).
            events.append(self._phase_event(len(events), phase_id, state, result, dispatched))

            if result.status in (GateStatus.FAILED, GateStatus.WARNING) and not hard_failed:
                final_status = GateStatus.WARNING
            if result.status == GateStatus.FAILED and budget_mode is BudgetMode.STRICT:
                final_status = GateStatus.FAILED
                break

        run_result = HarnessRunResult(
            run_id=state.run_id,
            workflow=workflow,
            task=task,
            status=final_status,
            ledgers=list(state.ledgers),
            gates=list(state.gates),
            artifacts=list(state.artifacts),
            decisions=list(state.decisions),
            trace_ids=list(state.trace_ids),
            warnings=list(state.warnings),
            events=list(events),
        )

        self.persist_run(state, run_result)
        self._post_run_update(state)
        return run_result

    def _post_run_update(self, state: HarnessState) -> None:
        """Re-index changed files after a run.

        Memory harvesting is handled by ArchivePhase (MemoryHarvester); the old
        harvest block here referenced a non-existent module and never ran.
        """
        changed = [
            e["path"] if isinstance(e, dict) else getattr(e, "path", str(e))
            for e in (state.apply_edits or [])
        ]
        # The model often writes through the host agent (no apply_edits recorded),
        # so fall back to the working tree's actual changes — the KG must reflect
        # what the task touched, whoever wrote it.
        if not changed:
            changed = self._git_changed_files(state.root)

        # Graph re-index of changed files only
        if changed:
            try:
                from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
                from opencontext_core.indexing.project_indexer import _KG_EXTENSIONS

                # Canonical KG db name — same as runtime/explore (context_graph.db).
                db_path = state.root / ".storage" / "opencontext" / "context_graph.db"
                kg_changed = {p for p in changed if (state.root / p).suffix in _KG_EXTENSIONS}
                if db_path.exists() and kg_changed:
                    kg = KnowledgeGraph(db_path=db_path)
                    try:
                        # reindex_files re-parses, rebuilds FTS, AND finalizes
                        # cross-file edges — the manual per-file loop skipped the
                        # last step, leaving call edges (which power graph ranking)
                        # stale after every task. Covers every KG language (not just
                        # .py) so JS/TS/Go/Rust/Java/PHP edits also refresh the graph.
                        kg.reindex_files(kg_changed, state.root)
                    except Exception as exc:
                        _log.warning("post-run re-index failed: %s", exc)
                    kg.close()
            except Exception:
                pass

    @staticmethod
    def _git_changed_files(root: Path) -> list[str]:
        """Working-tree changes (modified + untracked), relative paths. Best-effort."""
        import subprocess

        try:
            out = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            return []
        if out.returncode != 0:
            return []
        paths: list[str] = []
        for line in out.stdout.splitlines():
            entry = line[3:].strip()  # strip the "XY " status prefix
            if " -> " in entry:  # rename: keep the new path
                entry = entry.split(" -> ", 1)[1]
            if entry:
                paths.append(entry)
        return paths

    @staticmethod
    def _inputs_summary(state: HarnessState) -> str:
        """Deterministic one-line summary of a phase action's inputs."""
        return f"task={state.task!r} edits={len(getattr(state, 'apply_edits', []) or [])}"

    def _phase_event(
        self,
        index: int,
        phase_id: str,
        state: HarnessState,
        result: PhaseResult,
        dispatched: list[PhaseGate],
    ) -> RunEvent:
        """Build the typed action/observation event for an executed phase."""
        status = result.status.value if hasattr(result.status, "value") else str(result.status)
        gate_total = len(result.gates) + len(dispatched)
        failed = sum(1 for g in (*result.gates, *dispatched) if g.status == GateStatus.FAILED)
        observation = (
            f"phase '{phase_id}' -> {status}; "
            f"{len(result.artifacts)} artifact(s), {gate_total} gate(s), {failed} failed"
        )
        metadata: dict[str, Any] = {
            "artifacts": len(result.artifacts),
            "gates": gate_total,
            "failed_gates": failed,
        }
        if result.trace_id:
            metadata["trace_id"] = result.trace_id
        return RunEvent(
            index=index,
            phase=phase_id,
            action="run_phase",
            inputs_summary=self._inputs_summary(state),
            status=status,
            observation=observation,
            metadata=metadata,
        )

    def _harness_governance(self) -> tuple[str, bool]:
        """Resolve effective (tdd_mode, approval_required_for_writes).

        Prefers the harness dataclass config; when those are at their defaults,
        falls back to the top-level ``opencontext.yaml`` ``harness:`` section so
        TDD/approval can be configured from the main config too. Decoupled from
        token ``budget_mode``.
        """
        tdd_mode = getattr(self.config, "tdd_mode", "ask")
        approval_required = bool(getattr(self.config, "approval_required_for_writes", False))

        # Merge from the top-level config only to fill in non-overridden defaults.
        if tdd_mode == "ask" and not approval_required:
            try:
                from opencontext_core.config import load_config_or_defaults

                cfg = load_config_or_defaults(self.root / "opencontext.yaml")
                harness_cfg = getattr(cfg, "harness", None)
                if harness_cfg is not None:
                    if tdd_mode == "ask":
                        tdd_mode = getattr(harness_cfg, "tdd_mode", tdd_mode)
                    if not approval_required:
                        approval_required = bool(
                            getattr(harness_cfg, "approval_required_for_writes", False)
                        )
            except Exception:
                pass  # config is optional; fall back to harness-config defaults

        return tdd_mode, approval_required

    def _evaluate_apply_pre_gates(
        self, state: HarnessState, phase_config: Any
    ) -> tuple[list[PhaseGate], bool]:
        """Evaluate the apply PRE-gates (approval + TDD) before any file edit.

        Returns the list of evaluated pre-gates and whether the apply phase MUST
        be blocked (any pre-gate FAILED). Driven by config, not budget_mode.
        """
        gates: list[PhaseGate] = []
        blocked = False
        declared = set(getattr(phase_config, "gates", []) or [])
        tdd_mode, approval_required = self._harness_governance()

        # Human-approval pre-gate. Runs when declared OR when approval is required.
        if "approval_required_for_writes" in declared or approval_required:
            approved = "apply" in getattr(state, "approved_phases", set())
            gate = ApprovalRequiredForWritesGate().evaluate(
                approval_required=approval_required, approved=approved
            )
            gates.append(gate)
            if gate.status == GateStatus.FAILED:
                blocked = True

        # TDD failing-test pre-gate (red before green). Only blocks in strict mode.
        if "failing_test_exists" in declared or tdd_mode == "strict":
            gate = FailingTestExistsGate().evaluate(state.task, state.root)
            # Only strict mode enforces blocking; otherwise downgrade to WARNING.
            if tdd_mode == "strict":
                gates.append(gate)
                if gate.status == GateStatus.FAILED:
                    blocked = True
            elif tdd_mode == "off":
                # tdd off: do not gate apply on tests at all.
                pass
            else:  # "ask": surface as a non-blocking signal
                if gate.status == GateStatus.FAILED:
                    gates.append(
                        PhaseGate(
                            id=gate.id,
                            phase="apply",
                            status=GateStatus.WARNING,
                            message=gate.message,
                            metadata=gate.metadata,
                        )
                    )
                else:
                    gates.append(gate)

        return gates, blocked

    def _dispatch_declared_gates(
        self,
        state: HarnessState,
        phase_id: str,
        phase_config: Any,
        result: PhaseResult,
    ) -> list[PhaseGate]:
        """Run the config-declared gates for a phase via the existing gate classes.

        Skips gates already emitted by the phase or handled as apply pre-gates
        (approval/TDD), and gates that have no dispatch binding here.
        """
        if phase_config is None:
            return []
        declared = list(getattr(phase_config, "gates", []) or [])
        if not declared:
            return []

        already = {g.id for g in result.gates}
        # Approval + TDD are dispatched as apply PRE-gates, never here.
        skip = {"approval_required_for_writes", "failing_test_exists"}

        dispatched: list[PhaseGate] = []
        for gate_id in declared:
            if gate_id in already or gate_id in skip:
                continue
            gate = self._dispatch_one_gate(gate_id, phase_id, state, result)
            if gate is not None:
                dispatched.append(gate)
        return dispatched

    def _dispatch_one_gate(
        self,
        gate_id: str,
        phase_id: str,
        state: HarnessState,
        result: PhaseResult,
    ) -> PhaseGate | None:
        """Invoke a single declared gate class with state-derived inputs.

        Inputs are derived deterministically from run state. Gates that require
        external context default to safe, passing inputs (no external provider,
        no confidential export) so a declared-but-uninstrumented gate does not
        fabricate a failure. Returns None for gate ids with no binding here.
        """
        operation = self._operation_for_phase(phase_id)
        provider = operation.get("provider", "local")
        is_external = provider not in ("local", "opencontext-kg", "pytest")
        classification = operation.get("data_classification", "internal")
        has_confidential = classification in ("confidential", "secret", "regulated")

        if gate_id == "security_scan_passed":
            findings = self._scan_phase_artifacts(state, result)
            return SecurityScanPassedGate().evaluate(findings)
        if gate_id == "no_high_risk_exports":
            # No external send happens on the local path → no high-risk export.
            return NoHighRiskExportsGate().evaluate(
                has_confidential=has_confidential, is_external_provider=is_external
            )
        if gate_id == "provider_policy_passed":
            items_count = len(result.artifacts)
            return ProviderPolicyPassedGate().evaluate(
                provider=provider, is_external=is_external, items_count=items_count
            )
        if gate_id == "no_secret_leakage":
            return NoSecretLeakageGate().evaluate(self._artifact_text(result))
        if gate_id == "trace_id_created":
            return TraceIdCreatedGate().evaluate(state.trace_ids[-1] if state.trace_ids else None)
        if gate_id == "included_sources_present":
            return IncludedSourcesPresentGate().evaluate(
                getattr(state, "context_required_sources", []),
                getattr(state, "context_sources", set()),
            )
        if gate_id == "omissions_recorded":
            return OmissionsRecordedGate().evaluate(
                getattr(state, "context_omitted", 0),
                getattr(state, "context_omissions_recorded", 0),
            )
        if gate_id == "review_artifact_created":
            run_dir = state.root / self.config.artifact_root / state.run_id
            return ReviewArtifactCreatedGate().evaluate(run_dir)
        # Unknown / unbound declared gate: do not fabricate a result.
        return None

    @staticmethod
    def _artifact_text(result: PhaseResult) -> str:
        """Concatenate this phase's artifact file contents for secret scanning."""
        chunks: list[str] = []
        for artifact in result.artifacts:
            path = Path(artifact.path)
            try:
                if path.exists() and path.is_file() and path.stat().st_size < 200_000:
                    chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
        return "\n".join(chunks)

    @staticmethod
    def _scan_phase_artifacts(state: HarnessState, result: PhaseResult) -> list[str]:
        """Scan this phase's artifact files for secret findings (best-effort)."""
        try:
            from opencontext_core.safety.secrets import SecretScanner

            scanner = SecretScanner()
        except Exception:
            return []
        findings: list[str] = []
        for artifact in result.artifacts:
            path = Path(artifact.path)
            try:
                if path.exists() and path.is_file() and path.stat().st_size < 200_000:
                    hits = scanner.scan(path.read_text(encoding="utf-8", errors="ignore"))
                    findings.extend(str(h) for h in hits)
            except Exception:
                continue
        return findings

    def _build_phase(self, phase_id: str, budget_mode: BudgetMode) -> HarnessPhase | None:
        """Build a phase instance by ID."""
        phase_config = self.config.phases.get(phase_id)
        if phase_config is None:
            return None

        memory_store = getattr(self, "_memory_store", None)
        if phase_id == "explore":
            return ExplorePhase(phase_config, budget_mode, memory_store=memory_store)
        if phase_id == "propose":
            return ProposePhase(phase_config, budget_mode)
        if phase_id == "spec":
            return SpecPhase(phase_config, budget_mode)
        if phase_id == "design":
            return DesignPhase(phase_config, budget_mode)
        if phase_id == "tasks":
            return TasksPhase(phase_config, budget_mode)
        if phase_id == "apply":
            return ApplyPhase(
                phase_config, budget_mode, forbidden_paths=self.config.forbidden_paths
            )
        if phase_id == "verify":
            return VerifyPhase(phase_config, budget_mode)
        if phase_id == "review":
            return ReviewPhase(phase_config, budget_mode)
        if phase_id == "archive":
            return ArchivePhase(phase_config, budget_mode, memory_store=memory_store)
        if phase_id == "judgment":
            return JudgmentDayPhase(phase_config, budget_mode)
        if phase_id == "gga":
            return GGARulesPhase(phase_config, budget_mode)

        # Fallback: return None for unknown phases
        return None

    def _load_privacy_rules(self) -> list[PrivacyRule]:
        """Load privacy rules from .opencontext/privacy.yaml if present."""
        try:
            import yaml

            privacy_path = self.root / ".opencontext" / "privacy.yaml"
            if not privacy_path.exists():
                return []
            data = yaml.safe_load(privacy_path.read_text(encoding="utf-8"))
            rules_data = data.get("privacy_rules", []) if isinstance(data, dict) else []
            return [PrivacyRule(**r) for r in rules_data]
        except Exception:
            return []

    def _operation_for_phase(self, phase_id: str) -> dict[str, str]:
        """Return the operation descriptor for a given phase.

        Includes scope, provider, and data_classification when relevant.
        The data_classification field is used by PrivacyRule.evaluate() to
        enforce classification-based thresholds (e.g., block SENSITIVE+ on
        external_calls).
        """
        # Map phase IDs to operation scope/provider pairs
        # data_classification: the default classification for data accessed/written
        # by this phase — used by PrivacyGate to enforce classification thresholds
        phase_ops = {
            "explore": {
                "scope": "external_calls",
                "provider": "opencontext-kg",
                "data_classification": "internal",
            },
            "propose": {
                "scope": "external_calls",
                "provider": "opencontext-propose",
                "data_classification": "internal",
            },
            "spec": {
                "scope": "file_read",
                "provider": "local",
                "data_classification": "internal",
            },
            "design": {
                "scope": "file_read",
                "provider": "local",
                "data_classification": "internal",
            },
            "tasks": {
                "scope": "file_read",
                "provider": "local",
                "data_classification": "internal",
            },
            "apply": {
                "scope": "file_write",
                "provider": "local",
                "data_classification": "confidential",  # writes may expose sensitive data
            },
            "verify": {
                "scope": "network_call",
                "provider": "pytest",
                "data_classification": "internal",
            },
            "review": {
                "scope": "file_read",
                "provider": "local",
                "data_classification": "internal",
            },
            "archive": {
                "scope": "file_write",
                "provider": "local",
                "data_classification": "internal",
            },
        }
        default_op = {
            "scope": "file_read",
            "provider": "local",
            "data_classification": "internal",
        }
        return phase_ops.get(phase_id, default_op)

    def _warn_if_kg_not_indexed(self, state: HarnessState) -> None:
        """Add a warning if the knowledge graph has no indexed content.

        ExplorePhase depends on the KG. If it is empty, the explore phase
        will produce degraded results. Warn early rather than failing silently.
        """
        try:
            from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

            kg = KnowledgeGraph()
            stats = kg.get_stats()
            kg.close()
            if stats.get("nodes", 0) == 0:
                state.warnings.append(
                    "knowledge-graph: no content indexed — "
                    "run 'opencontext index' first for best explore results"
                )
        except Exception:
            # Never fail due to KG check failures
            pass

    def persist_run(self, state: HarnessState, result: HarnessRunResult) -> Path:
        """Persist run artifacts to .opencontext/runs/<run_id>/."""
        run_dir = self.root / ".opencontext" / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        def _serialize(obj: Any) -> Any:
            if hasattr(obj, "model_dump"):
                return obj.model_dump(mode="json")
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _serialize(v) for k, v in vars(obj).items()}
            if isinstance(obj, (BudgetMode, GateStatus)):
                return obj.value if hasattr(obj, "value") else str(obj)
            if isinstance(obj, list):
                return [_serialize(i) for i in obj]
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            return obj

        files = {
            "run.json": {
                "run_id": result.run_id,
                "workflow": result.workflow,
                "task": result.task,
                "status": (
                    result.status.value if hasattr(result.status, "value") else str(result.status)
                ),
                "created_at": result.created_at,
            },
            "ledger.json": {"ledgers": _serialize(result.ledgers)},
            "gates.json": {"gates": _serialize(result.gates)},
            "artifacts.json": {"artifacts": _serialize(result.artifacts)},
            "decisions.json": {"decisions": _serialize(result.decisions)},
            "events.json": {"events": _serialize(result.events)},
        }
        for filename, data in files.items():
            (run_dir / filename).write_text(
                json.dumps(data, indent=2, default=str), encoding="utf-8"
            )
        return run_dir
