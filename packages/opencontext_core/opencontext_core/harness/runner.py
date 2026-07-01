"""HarnessRunner — orchestrates workflow execution with phase governance."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    # Type-only import: the quality package imports harness.models, so importing
    # it at runtime here would create a cycle. The gate code imports
    # QualityEvaluator lazily (inside the dispatch branch); this annotation never
    # triggers a runtime import thanks to `from __future__ import annotations`.
    from opencontext_core.quality.models import HealthScore

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
from opencontext_core.workflow.delegation_validator import (
    DelegationValidationError,
    DelegationValidator,
)

_log = logging.getLogger(__name__)
_delegation_validator = DelegationValidator()


class HarnessState:
    """Mutable state accumulated during a harness run."""

    def __init__(self, run_id: str, root: Path, task: str = "", max_tokens: int = 6000) -> None:
        self.run_id = run_id
        self.root = root
        self.task = task
        self.max_tokens = max_tokens
        # PR-002 durable evidence layer. ``session_id`` scopes the on-disk
        # sessions/<id>/runs/<run_id> tree; ``durable_artifacts`` gates the whole
        # layer (off = PR-001 flat dump). Both are populated by ``create_run``.
        self.session_id: str = ""
        self.durable_artifacts: bool = False
        # Strict SDD posture (runtime.sdd_strict). When True a phase whose output
        # is a detected scaffold/placeholder is FAILED (blocking) rather than
        # WARNed (spec PR-004 SDD-CONV). Default False = legacy advisory posture.
        self.sdd_strict: bool = False
        # PR-000 ProgramPlan attached to the run for meta-plan-aware phase scoping
        # (spec PR-004 SDD-CONV). None when no program plan is present.
        self.program_plan: Any = None
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
        # Explore-phase debug metadata. Populated by :class:`ExplorePhase` so the
        # archiver / ``persist_run`` can write the surgical-vs-broad arm choice into
        # the persisted ``run.json`` (auditability: \"why did this run use the broad
        # pack?\"). Defaults mirror the zero-config defaults so non-explore runs
        # also persist harmlessly.
        self.explore_arm: str = "OC-SURGICAL"
        self.explore_expanded: bool = False
        self.explore_surgical_tokens: int = 0
        self.explore_broad_tokens: int = 0
        self.explore_kg_available: bool = False
        self.explore_arm_metadata: dict[str, Any] = {}
        # Omitted source paths from the context pack — used by the harvester to
        # populate the FAILURE:missing_context linked_nodes so a future run's
        # ``recent_failure`` boost can actually activate (``pack.omitted`` only
        # carried an integer count into ``state.context_omitted``).
        self.context_omitted_paths: list[str] = []
        # Architecture-health baseline captured at explore (run start) from the
        # knowledge graph, diffed by the verify-phase architecture_clean gate.
        # None until explore snapshots it (best-effort); a None baseline makes the
        # verify gate SKIPPED rather than reporting a false "clean". The dict
        # mirror is the JSON-safe view fed to the trace/serialization.
        self.architecture_baseline: HealthScore | None = None
        self.architecture_baseline_dict: dict[str, Any] = {}


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

        # PR-003 workflow registry rollback flag (pr-000-0 CL-005). Default off →
        # legacy _WORKFLOW_TRACK_ALIASES/WORKFLOW_TRACKS resolution runs verbatim
        # (spec FLAG1). Read defensively so an absent runtime block is harmless.
        self._registry_enabled = False
        self._durable_artifacts = False
        self._memory_v2 = False
        self._sdd_runner_v2 = False  # PR4.a: delegate to opencontext_sdd.runner when True
        # Strict SDD scaffold-blocking posture (runtime.sdd_strict, spec PR-004
        # SDD-CONV). Default off → legacy advisory scaffold reporting.
        self._sdd_strict = False
        self._workflow_registry: Any = None

        # Agent memory store. This MUST resolve to the same DB (path + provider)
        # the runtime's recall path reads, or every harvested memory lands in a
        # store recall never opens (write-only memory). The runtime recalls from
        # .storage/opencontext honoring memory.provider; resolve the same way
        # here from the project config instead of a hardcoded-local store under
        # .opencontext.
        try:
            from opencontext_core.backends.factory import BackendFactory
            from opencontext_core.config import load_config_or_defaults

            oc_config = load_config_or_defaults(self.root / "opencontext.yaml", auto_detect=False)
            self._registry_enabled = bool(
                getattr(getattr(oc_config, "runtime", None), "registry_enabled", False)
            )
            # PR-002 durable evidence layer flag (default off → PR-001 flat dump).
            self._durable_artifacts = bool(
                getattr(getattr(oc_config, "runtime", None), "durable_artifacts", False)
            )
            self._sdd_strict = bool(
                getattr(getattr(oc_config, "runtime", None), "sdd_strict", False)
            )
            # PR-009 Memory v2: route harvested writes through the MemoryHarness
            # (sole durable writer). Default off → legacy direct harvester writes.
            self._memory_v2 = bool(
                getattr(getattr(oc_config, "runtime", None), "memory_v2_enabled", False)
            )
            try:
                from opencontext_core.paths import resolve_storage_path

                storage_path = resolve_storage_path(
                    self.root,
                    oc_config.storage.mode,
                    oc_config.storage.custom_path,
                )
            except Exception:
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
            max_tokens=self.config.max_context_tokens,
        )
        # PR-002: mint a session id and propagate the durable flag. The session
        # tree is only materialised when durable_artifacts is on (ApplyPhase /
        # persist_run guard on state.durable_artifacts), so this is a no-op
        # otherwise and the PR-001 flat dump is unaffected.
        from opencontext_core.runtime.ids import new_session_id

        state.session_id = new_session_id()
        state.durable_artifacts = self._durable_artifacts
        state.sdd_strict = self._sdd_strict
        # Meta-plan awareness: attach a PR-000 ProgramPlan when one is present so
        # the work phases can seed scope from it (canonical phase order preserved).
        state.program_plan = self._load_program_plan()
        delegate = self._build_executor()
        if delegate is not None:
            state.delegate = delegate
        return state

    def _load_program_plan(self) -> Any:
        """Load a PR-000 ``ProgramPlan`` for this run root, or ``None`` if absent.

        Reads ``.opencontext/program-plan.json`` (the canonical drop location for
        a program plan the SDD flow should consume). Best-effort: a missing or
        unparseable file yields ``None`` so a run without a plan is unaffected
        (spec PR-004 SDD-CONV: meta-plan awareness).
        """
        try:
            path = self.root / ".opencontext" / "program-plan.json"
            if not path.exists():
                return None
            from opencontext_core.planning.program import ProgramPlan

            return ProgramPlan.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:  # advisory — never break a run on a bad plan file
            _log.warning("program plan load failed (advisory): %s", exc)
            return None

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

    def _validate_phase_delegation_result(
        self,
        result: Any,
        *,
        phase: str,
        requires_envelope: bool = False,
        expected_artifacts: list[str] | None = None,
    ) -> None:
        """Validate a sub-agent result returned by real delegation.

        LOCAL and MOCK delegation leave ``result.envelope=None``; this method is
        a no-op for those paths (``requires_envelope=False`` and no envelope
        present).  Only validates when the caller explicitly sets
        ``requires_envelope=True`` or when ``result.envelope`` is populated by a
        real delegated phase.

        Raises:
            DelegationValidationError: If the result fails validation.
        """
        has_envelope = getattr(result, "envelope", None) is not None
        if not requires_envelope and not has_envelope:
            return
        try:
            _delegation_validator.validate(
                result,
                requires_envelope=requires_envelope,
                expected_artifacts=expected_artifacts,
            )
        except DelegationValidationError as exc:
            _log.warning("phase %s delegation validation failed: %s", phase, exc)
            raise

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
    # DEPRECATED(2.0): legacy workflow alias resolution; superseded by the PR-003
    # WorkflowRegistry. runtime.registry_enabled is now default but this rollback path
    # remains; remove when the legacy track scheduler is removed (milestone-C).
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

    def _resolve_workflow(
        self, workflow: str, state: HarnessState
    ) -> tuple[list[str], list[RunEvent]]:
        """Resolve the phase order, optionally through the PR-003 registry.

        Flag off (default): returns the verbatim legacy ``schedule_phases`` order and
        no events (spec FLAG1). Flag on: resolves through ``WorkflowResolver``,
        emits ``workflow.alias_resolved`` (if an alias was used),
        ``workflow.validation.passed`` and ``workflow.resolved`` events (spec EVT1),
        writes the workflow-selection receipt (spec RCPT1), and returns the resolved
        order. Any resolver/validation failure falls back to the legacy order with a
        ``workflow.validation.failed`` event (task 3.2 fallback).
        """
        if not self._registry_enabled:
            return self.schedule_phases(workflow), []

        from opencontext_core.workflows import (
            WorkflowRegistry,
            WorkflowResolver,
        )
        from opencontext_core.workflows.resolver import WorkflowResolutionError
        from opencontext_core.workflows.validation import (
            WorkflowProfileError,
            WorkflowValidationError,
        )

        events: list[RunEvent] = []
        try:
            if self._workflow_registry is None:
                self._workflow_registry = WorkflowRegistry.with_builtins()
            resolver = WorkflowResolver(self._workflow_registry)
            resolved = resolver.resolve(workflow)
        except (WorkflowResolutionError, WorkflowValidationError, WorkflowProfileError) as exc:
            events.append(
                RunEvent(
                    index=0,
                    phase="workflow",
                    action="workflow.validation.failed",
                    inputs_summary=f"workflow={workflow}",
                    status="failed",
                    observation=f"registry resolution failed; using legacy path: {exc}",
                    metadata={"family": "workflow", "requested": workflow},
                )
            )
            return self.schedule_phases(workflow), events

        if resolved.alias_used:
            events.append(
                RunEvent(
                    index=len(events),
                    phase="workflow",
                    action="workflow.alias_resolved",
                    inputs_summary=f"alias={resolved.alias_used}",
                    status="passed",
                    observation=resolved.reason,
                    metadata={
                        "family": "workflow",
                        "alias": resolved.alias_used,
                        "workflow_id": resolved.definition.id,
                        "profile": resolved.profile,
                    },
                )
            )
        events.append(
            RunEvent(
                index=len(events),
                phase="workflow",
                action="workflow.validation.passed",
                inputs_summary=f"workflow={resolved.definition.id}",
                status="passed",
                observation=f"workflow {resolved.definition.id!r} passed validation",
                metadata={"family": "workflow", "workflow_uid": resolved.definition.uid},
            )
        )
        events.append(
            RunEvent(
                index=len(events),
                phase="workflow",
                action="workflow.resolved",
                inputs_summary=f"requested={workflow}",
                status="passed",
                observation=resolved.reason,
                metadata={
                    "family": "workflow",
                    "requested": resolved.requested,
                    "resolved": resolved.definition.id,
                    "workflow_uid": resolved.definition.uid,
                    "profile": resolved.profile,
                    "alias_used": resolved.alias_used,
                    "phase_order": list(resolved.phase_order),
                },
            )
        )
        self._write_selection_receipt(state, resolver.build_receipt(resolved))
        return list(resolved.phase_order), events

    def _write_selection_receipt(self, state: HarnessState, receipt: Any) -> None:
        """Persist the workflow-selection receipt into the run dir (spec RCPT1)."""
        try:
            run_dir = self.root / ".opencontext" / "runs" / state.run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "workflow-selection.json").write_text(
                json.dumps(receipt.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # advisory — must never fail the run
            _log.warning("workflow-selection receipt write failed (advisory): %s", exc)

    def completed_phases(self, run_id: str) -> set[str]:
        """Phases that finished (passed/warning) in a persisted run.

        Reads ``.opencontext/runs/<run_id>/events.json`` — the append-only phase
        ledger. A phase counts as completed only if its ``run_phase`` event has a
        passing outcome, so a failed/blocked phase is re-run on resume, not
        skipped. Returns an empty set when the run or ledger is absent.
        """
        import json as _json

        events_path = self.root / ".opencontext" / "runs" / run_id / "events.json"
        if not events_path.exists():
            return set()
        try:
            data = _json.loads(events_path.read_text(encoding="utf-8"))
        except (OSError, _json.JSONDecodeError):
            return set()
        done: set[str] = set()
        for event in data.get("events", []) if isinstance(data, dict) else []:
            if not isinstance(event, dict):
                continue
            if event.get("action") == "run_phase" and event.get("status") in ("passed", "warning"):
                phase = event.get("phase")
                if isinstance(phase, str):
                    done.add(phase)
        return done

    def run(
        self,
        workflow: str,
        task: str,
        budget_mode: BudgetMode = BudgetMode.WARN,
        *,
        apply_edits: list[Any] | None = None,
        approved_phases: set[str] | None = None,
        resume_from: str | None = None,
    ) -> HarnessRunResult:
        """Execute a full workflow with all phases.

        When ``_sdd_runner_v2`` is True, delegate to
        :func:`opencontext_sdd.runner.run_phase` for the SDD lifecycle
        instead of using the legacy inline phase loop.

        Args:
            workflow: Workflow name (sdd / explore-only / apply-only / ...).
            task: Task / change name.
            budget_mode: Token budget enforcement mode.
            apply_edits: Concrete file edits the executor produced, handed to
                ApplyPhase. Each item is a ``{"path", "content"}`` dict.
            approved_phases: Phases for which human approval has been granted.
                Used by the ``approval_required_for_writes`` pre-gate.
            resume_from: Run id of a prior run to resume. Phases that completed
                (passed/warning) in that run are skipped and recorded as
                ``skipped`` events in this run's ledger; execution picks up at the
                first incomplete phase.
                # NOTE (spec PR-004 REQ-10): a fresh run_id is minted on resume, so
                # the prior run's passed-phase artifacts are now rehydrated into
                # this run's dir via ``_carry_over_artifacts`` BEFORE the phase
                # loop, so a downstream phase (e.g. spec reading proposal.json)
                # resumed mid-flow finds the earlier phase's output and runs to
                # completion.
        """
        if self._sdd_runner_v2:
            return self._run_v2(workflow, task)

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

        # Single spine: resolve the phases to run. With runtime.registry_enabled on,
        # this routes through the PR-003 WorkflowRegistry (declarative resolution +
        # events + selection receipt) but still hands the resolved order to the
        # unchanged scheduler/executor below (spec INT1). With the flag off it is the
        # verbatim legacy DAG/track scheduler (PHASE_DEPENDENCIES / WORKFLOW_TRACKS).
        phase_ids, workflow_events = self._resolve_workflow(workflow, state)
        events.extend(workflow_events)

        # Resume: phases that already completed in a prior run are skipped here and
        # recorded as skipped events, so the ledger stays honest about what re-ran.
        resume_completed = self.completed_phases(resume_from) if resume_from else set()

        # REQ-10: rehydrate the prior run's passed-phase artifacts into THIS run's
        # dir before scheduling, so a downstream phase resumed mid-flow (e.g. spec
        # reading proposal.json) finds the earlier phase's output. create_run mints
        # a fresh run_id, so without this copy the resumed phase would not find it.
        if resume_from and resume_completed:
            self._carry_over_artifacts(resume_from, state.run_id, resume_completed)

        # PR-002 (RES-02): on the durable path, validate the prior run's manifest +
        # artifact integrity BEFORE scheduling any phase. A missing/corrupt required
        # artifact raises a typed ResumeIntegrityError here, aborting safely with no
        # state mutated. Off → legacy phase-skip resume (RES-01) is unchanged.
        if resume_from and self._durable_artifacts:
            from opencontext_core.harness.resume import ResumeManager
            from opencontext_core.harness.sessions import find_run_root

            prior_dir = find_run_root(self.root, resume_from)
            if prior_dir is not None and (prior_dir / "manifest.json").exists():
                ResumeManager(prior_dir).validate()

        for phase_id in phase_ids:
            if phase_id in resume_completed:
                events.append(
                    RunEvent(
                        index=len(events),
                        phase=phase_id,
                        action="skip_phase",
                        inputs_summary=f"resumed from {resume_from}",
                        status="skipped",
                        observation="phase already completed in the resumed run",
                    )
                )
                continue

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
                # Block-by-default: a FAILED verify-phase gate is fatal regardless
                # of budget_mode when gate_policy is "block" (the default). "warn"
                # keeps the historical posture (FAILED blocks only under STRICT).
                if budget_mode is BudgetMode.STRICT or self.config.gate_policy == "block":
                    final_status = GateStatus.FAILED
                elif not hard_failed:
                    final_status = GateStatus.WARNING

            # Record one typed event for this executed phase (action + observation).
            events.append(self._phase_event(len(events), phase_id, state, result, dispatched))

            # REQ-06 / SDD-CONV: emit one uniform per-phase decision receipt
            # (phase id, status, artifacts, gate digest, decisions) through the
            # PR-002 ReceiptStore, and a handoff artifact naming the next phase's
            # inputs. Both are advisory side-cars — they never alter run status.
            self._write_phase_receipt(state, phase_id, result, dispatched, workflow)
            self._write_handoff_artifact(state, phase_id, phase_ids, result, workflow)

            # Strict SDD posture (runtime.sdd_strict) blocks specifically on a
            # detected SCAFFOLD — the guardrail gate is FAILED only when the phase
            # produced a placeholder (spec PR-004 SDD-CONV). Other FAILED results
            # (e.g. explore's missing-index gates) keep the legacy WARNING posture.
            scaffold_blocked = getattr(state, "sdd_strict", False) and any(
                g.id == "guardrails" and g.status == GateStatus.FAILED for g in result.gates
            )
            contract_blocked = getattr(state, "sdd_strict", False) and any(
                g.id == "phase_contract" and g.status == GateStatus.WARNING
                for g in result.gates
            )
            if result.status == GateStatus.FAILED:
                if budget_mode is BudgetMode.STRICT or scaffold_blocked or contract_blocked:
                    final_status = GateStatus.FAILED
                    hard_failed = True
                    break
                if not hard_failed:
                    final_status = GateStatus.WARNING
            elif result.status == GateStatus.WARNING and not hard_failed:
                final_status = GateStatus.WARNING

        # Bounded apply->gate->fix loop: feed failing verify findings back to the
        # Builder for a re-attempt (revives quality rules' max_fix_loops). No-op
        # without a delegate / block policy / verify failure, so mock runs are
        # unaffected.
        final_status = self._run_fix_loops(state, final_status, events, budget_mode)

        # Risk-gated adversarial review: run the (deterministic) judgment phase for
        # high blast-radius changes that did not already schedule it. Advisory —
        # surfaces a judgment report without changing the run status.
        self._maybe_run_judgment(state, phase_ids, events, budget_mode)

        # ACON-lite feedback: record this run's retrieval omissions against its
        # outcome so the token optimizer can widen the "context_pack" budget when
        # omissions correlate with failures (explore consults that same budget).
        # Best-effort — learning must never block a run.
        try:
            from opencontext_core.learning.feedback_collector import FeedbackCollector
            from opencontext_core.paths import resolve_storage_path

            try:
                from opencontext_core.config import load_config_or_defaults

                _rc = load_config_or_defaults(state.root / "opencontext.yaml", auto_detect=False)
                _fb_base = resolve_storage_path(state.root, _rc.storage.mode, _rc.storage.custom_path)
            except Exception:
                _fb_base = state.root / ".storage" / "opencontext"
            fb = FeedbackCollector(storage_path=_fb_base / "learning")
            op_id = fb.start_operation("context_pack", task)
            fb.finish_operation(
                op_id,
                success=final_status == GateStatus.PASSED,
                context_items_omitted=int(getattr(state, "context_omitted", 0) or 0),
                context_items_selected=len(getattr(state, "context_sources", set()) or set()),
            )
        except Exception:
            pass

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
            context_omitted_paths=list(getattr(state, "context_omitted_paths", []) or []),
        )

        self.persist_run(state, run_result)
        self._post_run_update(state)
        self._post_run_evolution(state, run_result)
        return run_result

    # ------------------------------------------------------------------
    # PR4.a: v2 runner delegation
    # ------------------------------------------------------------------

    def _run_v2(self, workflow: str, task: str) -> HarnessRunResult:
        """Delegate SDD lifecycle to ``opencontext_sdd.runner.run_phase``.

        Called when ``_sdd_runner_v2`` is ``True``. Wraps the v2 result
        in a ``HarnessRunResult`` for backward compatibility with the
        existing telemetry and persistence chain.
        """
        try:
            from opencontext_sdd.runner import PhaseResultEnvelope, run_phase

            envelope = run_phase(workflow, change=task, cwd=str(self.root))
        except ImportError:
            envelope = type(
                "FallbackEnvelope",
                (),
                {
                    "status": "partial",
                    "executive_summary": "opencontext_sdd not installed; using legacy runner.",
                    "phase": workflow,
                },
            )()
        except Exception as exc:
            envelope = type(
                "FallbackEnvelope",
                (),
                {
                    "status": "failed",
                    "executive_summary": str(exc),
                    "phase": workflow,
                },
            )()

        # Fake a HarnessRunResult that downstream persistence can consume
        from dataclasses import dataclass

        @dataclass
        class _V2Result:
            run_id: str = ""
            workflow: str = workflow
            phases_ok: int = 1 if envelope.status == "ok" else 0
            phases_failed: int = 0 if envelope.status == "ok" else 1
            status: str = envelope.status
            executive_summary: str = envelope.executive_summary  # type: ignore[attr-defined]
            artifacts: dict = {}
            trace_id: str = ""

        return _V2Result()  # type: ignore[return-value]

    def _post_run_evolution(self, state: HarnessState, run_result: Any) -> None:
        """Generate and persist evolution proposals from the completed run.

        When ``config.learning.loop.enabled`` is ``True`` (PR-000.4, default off)
        this delegates to the unified, non-blocking ``LearningLoop`` (Decision Log
        + benchmark-gated learning candidates). Otherwise the legacy
        ``config.learning.in_loop`` propose-only evolution hook runs unchanged.
        Any exception is swallowed and appended as a warning — this hook MUST NOT
        abort or modify the run result.
        """
        try:
            loop_cfg = getattr(getattr(self.config, "learning", None), "loop", None)
            if loop_cfg is not None and getattr(loop_cfg, "enabled", False):
                try:
                    from opencontext_core.learning.loop import LearningLoop

                    LearningLoop(state.root, config=self.config).run_after(run_result)
                except Exception as _loop_exc:  # non-blocking — never abort the run
                    state.warnings.append(f"learning-loop: {_loop_exc}")
                return

            in_loop = bool(getattr(getattr(self.config, "learning", None), "in_loop", False))
            if not in_loop:
                return

            from opencontext_core.learning.evolution_engine import EvolutionEngine
            from opencontext_core.learning.evolution_store import EvolutionStore

            learned_patterns: list[Any] = []
            optimized_budgets: list[Any] = []
            memories_written: list[Any] = []

            # Optionally call LearningOrchestrator if available
            try:
                from opencontext_core.learning.learning_orchestrator import LearningOrchestrator

                try:
                    from opencontext_core.config import load_config_or_defaults
                    from opencontext_core.paths import resolve_storage_path

                    _lrc = load_config_or_defaults(state.root / "opencontext.yaml", auto_detect=False)
                    _ls = resolve_storage_path(state.root, _lrc.storage.mode, _lrc.storage.custom_path)
                except Exception:
                    _ls = state.root / ".storage" / "opencontext"
                orch = LearningOrchestrator(
                    storage_path=_ls / "learning",
                    kg_db_path=_ls / "context_graph.db",
                )
                orch.learn()
                learned_patterns = list(orch.patterns.get_all_patterns().values())
                optimized_budgets = list(orch.optimizer._budgets.values())
            except Exception as _lo_exc:
                _log.debug("post-run-evolution: LearningOrchestrator unavailable: %s", _lo_exc)

            engine = EvolutionEngine()
            proposals = engine.propose_from_run(
                run_result=run_result,
                learned_patterns=learned_patterns or None,
                optimized_budgets=optimized_budgets or None,
                memories_written=memories_written or None,
            )

            if proposals:
                store = EvolutionStore(state.root)
                for proposal in proposals:
                    store.save(proposal)
                _log.debug(
                    "post-run-evolution: saved %d proposal(s) to EvolutionStore",
                    len(proposals),
                )

        except Exception as _ev_exc:
            state.warnings.append(f"post-run-evolution: {_ev_exc}")
            _log.warning("post-run-evolution failed (non-fatal): %s", _ev_exc)

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
                try:
                    from opencontext_core.config import load_config_or_defaults
                    from opencontext_core.paths import resolve_storage_path

                    _krc = load_config_or_defaults(state.root / "opencontext.yaml", auto_detect=False)
                    _ks = resolve_storage_path(state.root, _krc.storage.mode, _krc.storage.custom_path)
                    db_path = _ks / "context_graph.db"
                except Exception:
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

    def _write_phase_receipt(
        self,
        state: HarnessState,
        phase_id: str,
        result: PhaseResult,
        dispatched: list[PhaseGate],
        workflow: str,
    ) -> None:
        """Emit one uniform per-phase decision receipt via the PR-002 ReceiptStore.

        Records phase id, status, the artifacts the phase produced, a gate digest
        (gate id -> status across phase + dispatched gates), the phase's declared
        required harnesses, the decisions that drove it and the trace id (spec
        PR-004 REQ-06 / SDD-CONV phase-level decision receipts). Advisory: a write
        failure is logged and never fails the run.
        """
        try:
            from opencontext_core.harness.receipt_store import ReceiptStore
            from opencontext_core.models.receipt import PhaseReceipt

            run_dir = self.root / ".opencontext" / "runs" / state.run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            gate_digest = {
                g.id: (g.status.value if hasattr(g.status, "value") else str(g.status))
                for g in (*result.gates, *dispatched)
            }
            phase_config = self.config.phases.get(phase_id)
            required = list(getattr(phase_config, "required_harnesses", []) or [])
            receipt = PhaseReceipt(
                run_id=state.run_id,
                session_id=getattr(state, "session_id", "") or "",
                workflow_id=workflow,
                phase=phase_id,
                status=result.status.value
                if hasattr(result.status, "value")
                else str(result.status),
                artifact_refs=[str(a.path) for a in result.artifacts],
                gate_digest=gate_digest,
                required_harnesses=required,
                decision_refs=[
                    str(getattr(d, "id", "")) for d in result.decisions if getattr(d, "id", "")
                ],
                trace_id=result.trace_id,
            )
            ReceiptStore(run_dir).write(receipt)
        except Exception as exc:  # advisory — must never fail the run
            _log.warning("phase receipt write failed for %s (advisory): %s", phase_id, exc)

    def _write_handoff_artifact(
        self,
        state: HarnessState,
        phase_id: str,
        phase_ids: list[str],
        result: PhaseResult,
        workflow: str,
    ) -> None:
        """Write a handoff artifact naming the next phase's inputs (SDD-CONV).

        Built as an ``AgentHandoff`` (run identity + the next phase's persona /
        required inputs / expected outputs from ``OC_NEW_FLOW``), projected onto
        the PR-006 ``PersonaHandoff`` view and persisted through the PR-002
        ``ArtifactStore`` (kind ``task-contract`` — a handoff is the input contract
        for the next phase). Only on a passed/warning transition with a real next
        phase. Advisory: a failure is logged and never fails the run.
        """
        try:
            if result.status not in (GateStatus.PASSED, GateStatus.WARNING):
                return
            try:
                idx = phase_ids.index(phase_id)
            except ValueError:
                return
            if idx + 1 >= len(phase_ids):
                return
            next_phase = phase_ids[idx + 1]

            from opencontext_core.harness.artifact_store import ArtifactStore
            from opencontext_core.models.artifact import ArtifactWriteRequest
            from opencontext_core.oc_new.flow import OC_NEW_FLOW
            from opencontext_core.personas import PHASE_PERSONAS
            from opencontext_core.personas.handoff import PersonaHandoff

            next_def = next((p for p in OC_NEW_FLOW if p.name == next_phase), None)
            required_inputs = list(getattr(next_def, "required_artifacts", []) or [])
            expected_outputs = list(getattr(next_def, "expected_artifacts", []) or [])

            from opencontext_core.oc_new.models import AgentHandoff

            handoff = AgentHandoff(
                run_id=state.run_id,
                change_id=state.task,
                trace_id=result.trace_id or "",
                phase=next_phase,  # type: ignore[arg-type]
                persona=PHASE_PERSONAS.get(next_phase, ""),
                task=state.task,
                memory_key=f"change:{state.task}",
                required_inputs=required_inputs,
                expected_outputs=expected_outputs,
                previous_phase_summary=f"{phase_id} completed with status {result.status}",
            )
            persona_handoff = PersonaHandoff.from_agent_handoff(
                handoff, from_persona=PHASE_PERSONAS.get(phase_id, "")
            )

            run_dir = self.root / ".opencontext" / "runs" / state.run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            ArtifactStore(run_dir).write(
                ArtifactWriteRequest(
                    run_id=state.run_id,
                    session_id=getattr(state, "session_id", "") or "",
                    workflow_id=workflow,
                    node_id=next_phase,
                    kind="task-contract",
                    content=persona_handoff.model_dump_json(indent=2),
                    media_type="application/json",
                    produced_by="HarnessRunner",
                    metadata={
                        "handoff": True,
                        "from_phase": phase_id,
                        "to_phase": next_phase,
                    },
                )
            )
        except Exception as exc:  # advisory — must never fail the run
            _log.warning("handoff artifact write failed after %s (advisory): %s", phase_id, exc)

    def _carry_over_artifacts(
        self, resume_from: str, new_run_id: str, resume_completed: set[str]
    ) -> None:
        """Copy a prior run's passed-phase artifacts into the resumed run's dir.

        Enumerates the prior run's passed-phase artifact files (via
        ``RunStore.passed_phase_artifacts``) and copies each, by basename, into the
        new run dir so downstream phases (e.g. spec reading ``proposal.json``) find
        the earlier phase's output (spec PR-004 REQ-10). Advisory: any failure is
        logged and never fails the run.
        """
        try:
            import shutil

            from opencontext_core.harness.run_store import RunStore

            new_dir = self.root / ".opencontext" / "runs" / new_run_id
            new_dir.mkdir(parents=True, exist_ok=True)
            for src in RunStore(self.root).passed_phase_artifacts(resume_from, resume_completed):
                dest = new_dir / src.name
                if not dest.exists():
                    shutil.copy2(src, dest)
        except Exception as exc:  # advisory — never break resume on a copy failure
            _log.warning("resume artifact carry-over failed (advisory): %s", exc)

    def _harness_governance(self) -> tuple[str, bool]:
        """Resolve effective (tdd_mode, approval_required_for_writes).

        Prefers the harness dataclass config; when those are at their defaults,
        falls back to the top-level ``opencontext.yaml`` ``harness:`` section so
        TDD/approval can be configured from the main config too. Decoupled from
        token ``budget_mode``.
        """
        import os

        _cfg_tdd = getattr(self.config, "tdd_mode", "ask")
        # Env var only applies when config is at the default ("ask"); an explicit
        # config value (e.g. from a test fixture) always wins.
        tdd_mode = os.environ.get("OPENCONTEXT_TDD_MODE", _cfg_tdd) if _cfg_tdd == "ask" else _cfg_tdd
        approval_required = bool(getattr(self.config, "approval_required_for_writes", False))

        # Merge from the top-level config only to fill in non-overridden defaults.
        if tdd_mode == "ask" and not approval_required:
            try:
                from opencontext_core.config import load_config_or_defaults

                cfg = load_config_or_defaults(self.root / "opencontext.yaml", auto_detect=False)
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
            else:  # "ask": non-interactive harness cannot ask, so fail closed.
                if gate.status == GateStatus.FAILED:
                    gates.append(
                        PhaseGate(
                            id=gate.id,
                            phase="apply",
                            status=GateStatus.FAILED,
                            message=(
                                "TDD gate requires a failing test. Continue, add test, "
                                "or switch mode? Non-interactive run blocked. "
                                + gate.message
                            ),
                            metadata=gate.metadata,
                        )
                    )
                    blocked = True
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
        if gate_id == "architecture_clean":
            return self._eval_architecture_gate(state, result)
        if gate_id == "quality_standards":
            return self._eval_quality_standards_gate(state, result)
        if gate_id == "tests_covered":
            return self._eval_test_gaps_gate(state, result)
        if gate_id == "code_economy":
            return self._eval_code_economy_gate(state, result)
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

    # -- architecture & code-quality gates (deterministic, zero model calls) --

    @staticmethod
    def _quality_db_path(root: Path) -> Path:
        """Path to the persisted knowledge graph the quality engine reads."""
        _local = root / ".storage" / "opencontext" / "context_graph.db"
        _oc_yaml = root / "opencontext.yaml"
        if not _oc_yaml.exists():
            return _local
        try:
            from opencontext_core.config import load_config_or_defaults
            from opencontext_core.paths import resolve_storage_path

            _qrc = load_config_or_defaults(_oc_yaml, auto_detect=False)
            _resolved = resolve_storage_path(root, _qrc.storage.mode, _qrc.storage.custom_path) / "context_graph.db"
            return _resolved if _resolved.exists() or not _local.exists() else _local
        except Exception:
            return _local

    # Working-tree paths that are byproducts / control-plane, NOT source the graph
    # is built from. These are written *after* (or independently of) the graph and
    # are not indexed, so a newer mtime here is NOT evidence the graph is stale:
    #   .storage/      — the DB itself + its WAL/shm sidecars + memory.db
    #   .opencontext/  — config (quality.toml), run artifacts, the quality baseline
    #   .git/          — VCS internals
    # All are excluded from indexing (DEFAULT_IGNORE_PATTERNS), so the staleness
    # check only considers changed SOURCE files.
    _STALE_IGNORE_PREFIXES: ClassVar[tuple[str, ...]] = (
        ".storage/",
        ".opencontext/",
        ".git/",
    )

    @classmethod
    def _graph_is_stale(cls, root: Path, changed_files: list[str]) -> bool:
        """True if the graph DB is OLDER than any changed SOURCE file.

        The apply->verify re-check relies on ApplyPhase's best-effort mid-flow
        reindex. If that silently failed the graph would not reflect the change
        and the gate would diff against a stale graph and report a false "clean".
        We detect that by comparing the DB mtime against the changed *source*
        files' mtimes: if a changed source file is newer than the graph, the
        graph is stale and the caller returns SKIPPED rather than a misleading
        PASS.

        Internal byproducts (``.storage/`` — including the DB's own WAL/shm
        sidecars and ``memory.db`` — ``.opencontext/runs/``, ``.git/``) are
        excluded: they are written by indexing/runs *after* the graph and would
        otherwise make every check spuriously "stale". Best-effort — an
        unreadable mtime is treated as "not stale" (the snapshot path itself
        degrades honestly downstream).
        """
        db_path = cls._quality_db_path(root)
        try:
            if not db_path.exists():
                return False
            db_mtime = db_path.stat().st_mtime
        except OSError:
            return False
        for rel in changed_files:
            norm = rel.replace("\\", "/")
            if norm.startswith(cls._STALE_IGNORE_PREFIXES):
                continue
            try:
                fp = root / rel
                if fp.exists() and fp.stat().st_mtime > db_mtime:
                    return True
            except OSError:
                continue
        return False

    def _eval_architecture_gate(self, state: HarnessState, result: PhaseResult) -> PhaseGate:
        """architecture_clean — diff post-apply health vs the explore snapshot.

        Recomputes a token-free architecture-only health snapshot over the fresh
        (post-apply) graph and diffs it against the baseline captured at explore.
        Calls ONLY the deterministic evaluator (graph analysis) — never the model
        / ``state.delegate``. Returns a WARNING on a health drop, PASSED when the
        score held or improved, and SKIPPED (with a reason) when there is no
        baseline or the graph is stale — never a false "clean".

        The dispatched gate fails the run only under ``BudgetMode.STRICT`` (see
        the gate-dispatch loop), which is exactly the WARN-by-default /
        FAIL-under-STRICT posture; this method itself does not decide that.
        """
        baseline = getattr(state, "architecture_baseline", None)
        if baseline is None:
            return PhaseGate(
                id="architecture_clean",
                phase="verify",
                status=GateStatus.SKIPPED,
                message="architecture: no explore baseline (snapshot unavailable)",
                metadata={"reason": "no-baseline"},
            )

        changed = self._git_changed_files(state.root)
        if not changed:
            return PhaseGate(
                id="architecture_clean",
                phase="verify",
                status=GateStatus.SKIPPED,
                message=(
                    "architecture: no changed files (non-git project, empty tree, "
                    "or no working-tree diff — snapshotting the whole repo can "
                    "mask regressions; scope the run with a git workflow for an "
                    "actual regression signal)"
                ),
                metadata={"reason": "no-changed-files"},
            )
        if self._graph_is_stale(state.root, changed):
            return PhaseGate(
                id="architecture_clean",
                phase="verify",
                status=GateStatus.SKIPPED,
                message="architecture: graph stale vs changed files (reindex incomplete)",
                metadata={"reason": "stale-graph"},
            )

        try:
            from opencontext_core.quality.evaluator import QualityEvaluator

            evaluator = QualityEvaluator(state.root)
            current = evaluator.snapshot(changed_files=changed)
            verdict = evaluator.evaluate_health_regression(baseline, current, evaluator.rules)
        except Exception as exc:  # pragma: no cover - best-effort, degrade honestly
            return PhaseGate(
                id="architecture_clean",
                phase="verify",
                status=GateStatus.SKIPPED,
                message=f"architecture: evaluation unavailable ({exc})",
                metadata={"reason": "error"},
            )

        delta = current.delta(baseline)
        message = f"architecture {baseline.score} -> {current.score}"
        if verdict.status.value == "passed":
            status = GateStatus.PASSED
        else:
            # The evaluator already encodes STRICT->error / else->warning in the
            # verdict severity; the run-level gate status surfaces WARNING and the
            # dispatch loop escalates to FAILED under BudgetMode.STRICT.
            # Under block policy (default) a health regression is fatal; under
            # warn it stays an advisory WARNING (the historical posture).
            status = (
                GateStatus.FAILED
                if verdict.severity.value in ("error", "critical")
                or self.config.gate_policy == "block"
                else GateStatus.WARNING
            )
        return PhaseGate(
            id="architecture_clean",
            phase="verify",
            status=status,
            message=message,
            metadata={
                "baseline": baseline.score,
                "current": current.score,
                "delta": delta,
                "components": dict(current.components),
                "new_findings": [
                    {
                        "rule": f.rule,
                        "severity": f.severity.value,
                        "message": f.message,
                        "file": f.file,
                        "line": f.line,
                    }
                    for f in verdict.findings
                ],
            },
        )

    def _eval_quality_standards_gate(self, state: HarnessState, result: PhaseResult) -> PhaseGate:
        """quality_standards — run the per-language tools over the changed scope.

        Runs the full :meth:`QualityEvaluator.evaluate` (architecture findings +
        the language tool subprocesses + the ratchet diff) on the changed files
        and maps the resulting :class:`QualityReport` status straight onto a
        :class:`PhaseGate`. Deterministic subprocess + graph work only — never the
        model. Like the architecture gate it only fails the run under
        ``BudgetMode.STRICT``; otherwise a violation is a WARNING fed to the
        Builder for the in-loop fix.
        """
        changed = self._git_changed_files(state.root)
        if not changed:
            return PhaseGate(
                id="quality_standards",
                phase="verify",
                status=GateStatus.SKIPPED,
                message=(
                    "quality: no changed files (non-git project, empty tree, "
                    "or no working-tree diff — running the full tool set would "
                    "report lots of pre-existing violations unrelated to this run)"
                ),
                metadata={"reason": "no-changed-files"},
            )
        if self._graph_is_stale(state.root, changed):
            return PhaseGate(
                id="quality_standards",
                phase="verify",
                status=GateStatus.SKIPPED,
                message="quality: graph stale vs changed files (reindex incomplete)",
                metadata={"reason": "stale-graph"},
            )
        try:
            from opencontext_core.quality.evaluator import QualityEvaluator

            evaluator = QualityEvaluator(state.root)
            report = evaluator.evaluate(changed)
        except Exception as exc:  # pragma: no cover - best-effort, degrade honestly
            return PhaseGate(
                id="quality_standards",
                phase="verify",
                status=GateStatus.SKIPPED,
                message=f"quality: evaluation unavailable ({exc})",
                metadata={"reason": "error"},
            )

        return PhaseGate(
            id="quality_standards",
            phase="verify",
            status=report.status,
            message=report.summary or f"quality {report.health.score}",
            metadata={
                "health": report.health.score,
                "findings": [
                    {
                        "rule": f.rule,
                        "severity": f.severity.value,
                        "message": f.message,
                        "file": f.file,
                        "line": f.line,
                        "category": f.category,
                    }
                    for f in report.new_findings
                ],
                "skipped": list(report.skipped),
            },
        )

    def _eval_test_gaps_gate(self, state: HarnessState, result: PhaseResult) -> PhaseGate:
        """tests_covered — warn when a changed symbol has no referencing test.

        Structural proxy (does any test file reference the symbol at all), scoped
        to the files this run changed so the change is judged on the code it
        touched, not the legacy repo. Deterministic graph read; never the model.
        SKIPs (never a false pass) when there is no changed scope, no graph, or the
        graph is stale. ADVISORY (WARNING) even under gate_policy="block": a
        structural gap is a softer signal than a regression or a leak — a symbol
        may be covered indirectly — so it surfaces the gap in-flow (scoped to the
        change) without blocking the run.
        """
        changed = self._git_changed_files(state.root)
        if not changed:
            return PhaseGate(
                id="tests_covered",
                phase="verify",
                status=GateStatus.SKIPPED,
                message="tests: no changed files (non-git, empty tree, or no diff)",
                metadata={"reason": "no-changed-files"},
            )
        db_path = self._quality_db_path(state.root)
        if not db_path.exists():
            return PhaseGate(
                id="tests_covered",
                phase="verify",
                status=GateStatus.SKIPPED,
                message="tests: no knowledge graph (run `opencontext index .` first)",
                metadata={"reason": "no-graph"},
            )
        if self._graph_is_stale(state.root, changed):
            return PhaseGate(
                id="tests_covered",
                phase="verify",
                status=GateStatus.SKIPPED,
                message="tests: graph stale vs changed files (reindex incomplete)",
                metadata={"reason": "stale-graph"},
            )
        try:
            from opencontext_core.indexing.graph_db import GraphDatabase

            scope = {c.replace("\\", "/") for c in changed}
            db = GraphDatabase(db_path)
            try:
                gaps = db.find_test_gaps(changed_files=scope)
            finally:
                db.close()
        except Exception as exc:  # pragma: no cover - best-effort, degrade honestly
            return PhaseGate(
                id="tests_covered",
                phase="verify",
                status=GateStatus.SKIPPED,
                message=f"tests: evaluation unavailable ({exc})",
                metadata={"reason": "error"},
            )

        if not gaps:
            return PhaseGate(
                id="tests_covered",
                phase="verify",
                status=GateStatus.PASSED,
                message="tests: every changed function/method is referenced by a test",
            )
        return PhaseGate(
            id="tests_covered",
            phase="verify",
            status=GateStatus.WARNING,
            message=f"tests: {len(gaps)} changed symbol(s) with no referencing test",
            metadata={
                "reason": "test-gaps",
                "count": len(gaps),
                "gaps": [
                    {
                        "name": g["name"],
                        "kind": g["kind"],
                        "file": g["file_path"],
                        "line": g["line"],
                    }
                    for g in gaps[:50]
                ],
            },
        )

    def _eval_code_economy_gate(self, state: HarnessState, result: PhaseResult) -> PhaseGate:
        """code_economy — warn on symbols added with no caller/importer/reference.

        Advisory (WARNING): an orphan symbol in the changed files is a strong hint
        of dead or speculative code (the category this review hunts), but a
        string-dispatched entry point can look orphan in the graph, so it surfaces
        the hit rather than blocking. SKIPs (never a false pass) without a changed
        scope / graph / fresh graph — mirrors tests_covered.
        """
        changed = self._git_changed_files(state.root)
        if not changed:
            return PhaseGate(
                id="code_economy",
                phase="verify",
                status=GateStatus.SKIPPED,
                message="economy: no changed files (non-git, empty tree, or no diff)",
                metadata={"reason": "no-changed-files"},
            )
        db_path = self._quality_db_path(state.root)
        if not db_path.exists():
            return PhaseGate(
                id="code_economy",
                phase="verify",
                status=GateStatus.SKIPPED,
                message="economy: no knowledge graph (run `opencontext index .` first)",
                metadata={"reason": "no-graph"},
            )
        if self._graph_is_stale(state.root, changed):
            return PhaseGate(
                id="code_economy",
                phase="verify",
                status=GateStatus.SKIPPED,
                message="economy: graph stale vs changed files (reindex incomplete)",
                metadata={"reason": "stale-graph"},
            )
        try:
            from opencontext_core.indexing.graph_db import GraphDatabase

            scope = {c.replace("\\", "/") for c in changed}
            db = GraphDatabase(db_path)
            try:
                unused = db.find_unused_symbols(changed_files=scope)
            finally:
                db.close()
        except Exception as exc:  # pragma: no cover - best-effort, degrade honestly
            return PhaseGate(
                id="code_economy",
                phase="verify",
                status=GateStatus.SKIPPED,
                message=f"economy: evaluation unavailable ({exc})",
                metadata={"reason": "error"},
            )

        if not unused:
            return PhaseGate(
                id="code_economy",
                phase="verify",
                status=GateStatus.PASSED,
                message="economy: no orphan symbols in the changed files",
            )
        return PhaseGate(
            id="code_economy",
            phase="verify",
            status=GateStatus.WARNING,
            message=f"economy: {len(unused)} changed symbol(s) with no caller/importer",
            metadata={
                "reason": "unused-symbols",
                "count": len(unused),
                "symbols": [
                    {
                        "name": u["name"],
                        "kind": u["kind"],
                        "file": u["file_path"],
                        "line": u["line"],
                    }
                    for u in unused[:50]
                ],
            },
        )

    # -- bounded apply->verify->fix loop (revives quality rules.max_fix_loops) --

    def _run_fix_loops(
        self,
        state: HarnessState,
        final_status: GateStatus,
        events: list[Any],
        budget_mode: BudgetMode,
    ) -> GateStatus:
        """Feed failing verify findings back to the Builder and re-attempt.

        Runs only when the run FAILED on verify-phase gates under block policy and
        a real executor is wired; otherwise returns ``final_status`` unchanged (so
        mock / no-model runs are untouched). Bounded by quality rules'
        ``max_fix_loops``: each attempt re-applies with the findings, reindexes,
        and re-verifies via the same gate dispatch. Returns the resolved status
        (PASSED/WARNING when verify recovers, else the original FAILED).
        """
        if final_status is not GateStatus.FAILED or self.config.gate_policy != "block":
            return final_status
        if getattr(state, "delegate", None) is None:
            return final_status
        failing = [g for g in state.gates if g.phase == "verify" and g.status == GateStatus.FAILED]
        if not failing:
            return final_status
        try:
            from opencontext_core.quality.evaluator import QualityEvaluator

            max_loops = int(QualityEvaluator(state.root).rules.max_fix_loops)
        except Exception:
            max_loops = 0

        for attempt in range(1, max_loops + 1):
            findings = self._collect_fix_findings(failing)
            self._reapply_with_findings(state, findings, budget_mode)
            new_verify_gates = self._reverify(state)
            still_failing = [g for g in new_verify_gates if g.status == GateStatus.FAILED]
            # Replace the stale verify gates with this attempt's fresh ones.
            state.gates = [g for g in state.gates if g.phase != "verify"] + new_verify_gates
            events.append(self._fix_loop_event(len(events), attempt, max_loops, still_failing))
            if not still_failing:
                state.warnings.append(f"fix-loop: verify recovered after {attempt} fix attempt(s)")
                return (
                    GateStatus.WARNING
                    if any(g.status == GateStatus.WARNING for g in new_verify_gates)
                    else GateStatus.PASSED
                )
            failing = still_failing
        state.warnings.append(f"fix-loop: still failing after {max_loops} fix attempt(s)")
        return final_status

    @staticmethod
    def _collect_fix_findings(gates: list[PhaseGate]) -> str:
        """Render failing verify-gate findings as a compact fix-instruction block."""
        lines: list[str] = []
        for g in gates:
            lines.append(f"- {g.id}: {g.message}")
            meta = g.metadata or {}
            rows = meta.get("new_findings") or meta.get("findings") or meta.get("symbols") or []
            for row in rows:
                loc = f"{row.get('file', '?')}:{row.get('line', '?')}"
                detail = row.get("message") or row.get("rule") or row.get("name") or ""
                lines.append(f"    {loc} {detail}".rstrip())
        return "\n".join(lines)

    def _reapply_with_findings(
        self, state: HarnessState, findings: str, budget_mode: BudgetMode
    ) -> None:
        """Re-generate apply edits with the findings appended, apply, and reindex.

        Overridable seam (tests stub it). Best-effort: a codegen/apply failure
        leaves prior state so the loop simply re-verifies and may exhaust.
        """
        original = state.context_pack
        try:
            state.context_pack = f"{original}\n\n## Gate findings to fix\n{findings}".strip()
            edits = self._generate_apply_edits(state)
        finally:
            state.context_pack = original
        if not edits:
            return
        state.apply_edits = edits
        apply_phase = self._build_phase("apply", budget_mode)
        if apply_phase is not None:
            try:
                apply_phase.run(state)
            except Exception as exc:  # pragma: no cover - degrade honestly
                state.warnings.append(f"fix-loop: re-apply failed: {exc}")
        self._post_run_update(state)

    def _reverify(self, state: HarnessState) -> list[PhaseGate]:
        """Re-dispatch the verify phase's declared gates against the fresh graph.

        Overridable seam (tests stub it). Returns the freshly-evaluated verify
        gates (architecture_clean / quality_standards / tests_covered / ...).
        """
        verify_config = self.config.phases.get("verify")
        if verify_config is None:
            return []
        synthetic = PhaseResult(phase="verify", status=GateStatus.PASSED)
        return list(self._dispatch_declared_gates(state, "verify", verify_config, synthetic))

    @staticmethod
    def _fix_loop_event(
        index: int, attempt: int, max_loops: int, still_failing: list[PhaseGate]
    ) -> Any:
        """A typed RunEvent for one fix-loop attempt."""
        return RunEvent(
            index=index,
            phase="verify",
            action="fix_attempt",
            inputs_summary=f"fix attempt {attempt}/{max_loops}",
            status=(GateStatus.FAILED.value if still_failing else GateStatus.PASSED.value),
            observation=(
                f"fix attempt {attempt}/{max_loops}: "
                + (
                    f"{len(still_failing)} gate(s) still failing"
                    if still_failing
                    else "verify recovered"
                )
            ),
            metadata={"attempt": attempt, "max_loops": max_loops},
        )

    # -- risk-gated adversarial review (auto-run judgment for high blast radius) --

    def _blast_radius_high(self, state: HarnessState) -> bool:
        """True when this change is high-risk enough to warrant adversarial review.

        Deterministic heuristic: touching a ``security/`` or ``safety/`` boundary is
        always high-risk; otherwise a broad change (many source files) is. No graph
        dependency, so it works even before/without an index.
        """
        changed = self._git_changed_files(state.root)
        if not changed:
            return False
        for rel in changed:
            norm = f"/{rel.replace(chr(92), '/')}"
            if "/security/" in norm or "/safety/" in norm:
                return True
        source = [
            c for c in changed if not c.replace("\\", "/").startswith(self._STALE_IGNORE_PREFIXES)
        ]
        return len(source) >= 8

    def _maybe_run_judgment(
        self,
        state: HarnessState,
        phase_ids: list[str],
        events: list[Any],
        budget_mode: BudgetMode,
    ) -> None:
        """Run the judgment phase for high blast-radius changes (advisory).

        No-op when the workflow already scheduled ``judgment`` or the blast radius
        is low. The judgment phase is deterministic (no LLM); its findings are
        appended as gates + a report, surfaced but NOT used to flip the run status.
        Best-effort: any failure is recorded as a warning, never raised.
        """
        if "judgment" in phase_ids:
            return
        if not self._blast_radius_high(state):
            return
        try:
            phase = self._build_phase("judgment", budget_mode)
            if phase is None:
                return
            result = phase.run(state)
        except Exception as exc:  # pragma: no cover - best-effort, degrade honestly
            state.warnings.append(f"risk-gated judgment skipped: {exc}")
            return
        state.gates.extend(result.gates)
        state.artifacts.extend(result.artifacts)
        events.append(
            RunEvent(
                index=len(events),
                phase="judgment",
                action="risk_gated_review",
                inputs_summary=self._inputs_summary(state),
                status=result.status.value,
                observation="high blast radius: ran adversarial judgment review",
                metadata={"trigger": "blast-radius"},
            )
        )
        if result.status in (GateStatus.FAILED, GateStatus.WARNING):
            state.warnings.append("risk-gated judgment surfaced findings (advisory)")

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
            return ArchivePhase(
                phase_config,
                budget_mode,
                memory_store=memory_store,
                memory_v2=getattr(self, "_memory_v2", False),
            )
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

            # Resolve DB path via StorageConfig. When an opencontext.yaml exists and
            # sets mode=user, use the XDG path. Otherwise fall back to the in-repo
            # local path for backward compatibility (legacy layout and tests without
            # a project config file).
            _local_kg_db = self.root / ".storage" / "opencontext" / "context_graph.db"
            _kg_db = _local_kg_db
            _oc_yaml = self.root / "opencontext.yaml"
            if _oc_yaml.exists():
                try:
                    from opencontext_core.config import load_config_or_defaults
                    from opencontext_core.paths import resolve_storage_path

                    _crc = load_config_or_defaults(_oc_yaml, auto_detect=False)
                    _cs = resolve_storage_path(self.root, _crc.storage.mode, _crc.storage.custom_path)
                    _kg_db = _cs / "context_graph.db"
                    if not _kg_db.exists() and _local_kg_db.exists():
                        _kg_db = _local_kg_db
                except Exception:
                    _kg_db = _local_kg_db
            kg = KnowledgeGraph(db_path=_kg_db)
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

        # Explore-phase debug metadata is surfaced via ``state`` so that
        # :class:`ArchivePhase` and a developer audit can answer "why did this run
        # use the broad pack?" without re-running the explore. The fields are
        # populated by :class:`ExplorePhase.run` (state.explore_arm, etc.); they
        # default to zero-explore-no-op values when not set so a workflow that
        # skips ``explore`` (``apply-only``, ``quick``) still persists cleanly.
        explore_meta = getattr(state, "explore_arm_metadata", {}) or {}
        if not explore_meta:
            explore_meta = {
                "arm": getattr(state, "explore_arm", "OC-SURGICAL"),
                "expanded": bool(getattr(state, "explore_expanded", False)),
                "surgical_tokens": int(getattr(state, "explore_surgical_tokens", 0) or 0),
                "broad_tokens": int(getattr(state, "explore_broad_tokens", 0) or 0),
                "kg_available": bool(getattr(state, "explore_kg_available", False)),
            }
        files = {
            "run.json": {
                "run_id": result.run_id,
                "workflow": result.workflow,
                "task": result.task,
                "status": (
                    result.status.value if hasattr(result.status, "value") else str(result.status)
                ),
                "created_at": result.created_at,
                "metadata": {
                    "explore": explore_meta,
                    "context_pack": {
                        "selected": len(getattr(state, "context_sources", set()) or set()),
                        "omitted": int(getattr(state, "context_omitted", 0) or 0),
                        "omitted_paths": list(getattr(state, "context_omitted_paths", []) or []),
                    },
                },
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

        # VerifyReport: serialized alongside the run artifacts when the verify phase ran.
        # Written only when a ComplianceMatrix was produced by VerifyPhase.
        try:
            verify_phase_result = next(
                (a for a in result.artifacts if getattr(a, "kind", "") == "verify-report"),
                None,
            )
            if verify_phase_result is not None:
                # Pull compliance matrix from run state metadata (set by VerifyPhase)
                # by inspecting gates for the compliance_matrix gate metadata.
                from opencontext_core.verify.compliance import ComplianceMatrix
                from opencontext_core.verify.report import VerifyReport

                _cm_data: Any = None
                for gate in result.gates:
                    if getattr(gate, "id", "") == "compliance_matrix":
                        _cm_data = (getattr(gate, "metadata", None) or {}).get("matrix")
                        break

                if _cm_data is not None:
                    _matrix = ComplianceMatrix.model_validate(_cm_data)
                    _vreport = VerifyReport.compute_verdict(_matrix)
                    _vreport_path = run_dir / "verify-report-compliance.json"
                    _vreport_path.write_text(
                        json.dumps(_vreport.model_dump(mode="json"), indent=2),
                        encoding="utf-8",
                    )
                    files["verify-report-compliance.json"] = _vreport.model_dump(mode="json")
        except Exception as _vr_exc:
            _log.warning("persist_run: VerifyReport write failed (advisory): %s", _vr_exc)

        # Index the run so `opencontext run list/show/artifacts` (and any API
        # consumer) can resolve run_id -> artifact dir without re-scanning disk.
        # Best-effort: a failed index write must not fail the run itself.
        try:
            from opencontext_core.harness.run_store import RunStore

            RunStore(self.root).register(state.run_id, run_dir)
        except Exception:
            # Indexing is advisory — a failed index write must not fail the run.
            pass

        # PR-002: when durable_artifacts is on, additionally materialise the
        # session run tree and write the immutable RunManifest indexing this run's
        # artifacts/receipts/checkpoints (MAN-01, SES-01). Additive to the flat
        # dump above so `run list/show` keep working; off → none of this runs.
        if self._durable_artifacts and state.session_id:
            try:
                from opencontext_core.harness.sessions import (
                    build_run_manifest,
                    ensure_layout,
                    write_run_manifest,
                )

                durable_dir = ensure_layout(self.root, state.session_id, state.run_id)
                events_rel = "events.jsonl"
                (durable_dir / events_rel).write_text(
                    "".join(e.model_dump_json() + "\n" for e in result.events),
                    encoding="utf-8",
                )
                status_str = (
                    result.status.value if hasattr(result.status, "value") else str(result.status)
                )
                manifest = build_run_manifest(
                    durable_dir,
                    session_id=state.session_id,
                    run_id=state.run_id,
                    workflow_id=result.workflow,
                    status=status_str,
                    events_path=events_rel,
                )
                write_run_manifest(durable_dir, manifest)
            except Exception as _man_exc:
                _log.warning("persist_run: durable manifest write failed (advisory): %s", _man_exc)

        return run_dir
