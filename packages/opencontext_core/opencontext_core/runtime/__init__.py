"""Runtime facade for indexing and workflow execution."""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.config import (
    OpenContextConfig,
    SecurityMode,
    default_config_data,
    load_config,
)
from opencontext_core.context.assembler import PromptAssembler
from opencontext_core.context.budgeting import TokenBudgetManager, estimate_tokens
from opencontext_core.context.compiler import ContextCompiler, evidence_to_context_item
from opencontext_core.context.compression import CompressionEngine
from opencontext_core.embeddings.extractors import items_from_manifest
from opencontext_core.embeddings.stores import LocalVectorStore, NullVectorStore
from opencontext_core.embeddings.worker import AsyncEmbeddingWorker, create_worker
from opencontext_core.errors import ConfigurationError, MemoryStoreError, WorkflowExecutionError
from opencontext_core.indexing.graph_tunnel import GraphTunnelStore
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.indexing.project_indexer import ProjectIndexer
from opencontext_core.indexing.repo_map import RepoMapEngine
from opencontext_core.learning.learning_orchestrator import (
    LearningOrchestrator,
    NullLearningOrchestrator,
)
from opencontext_core.llm.gateway import LLMGateway
from opencontext_core.llm.mock import MockLLMGateway
from opencontext_core.memory.stores import LocalProjectMemoryStore, ProjectMemoryStore
from opencontext_core.memory_usability.context_repository import ContextRepository
from opencontext_core.models.context import ContextItem, ContextPackResult
from opencontext_core.models.llm import LLMRequest, LLMResponse
from opencontext_core.models.project import ProjectManifest
from opencontext_core.models.trace import RuntimeTrace, TraceEvent, TraceSpan
from opencontext_core.operating_model.call_budget import (
    CallBudgetManager,
    FreeProviderRegistry,
)
from opencontext_core.operating_model.events import ProviderEventEmitter
from opencontext_core.operating_model.performance import CostLedger, ModelRoleRouter
from opencontext_core.operating_model.quality import PreLLMQualityGate
from opencontext_core.operating_model.receipts import RunReceiptStore
from opencontext_core.paths import (
    StorageMode,
    detect_legacy,
    resolve_storage_path,
    resolve_workspace_path,
    write_manifest,
)
from opencontext_core.project.profiles import TechnologyProfile
from opencontext_core.providers.gateway import ProviderGateway as UnifiedProviderGateway
from opencontext_core.retrieval.contracts import (
    EvidenceItem,
    EvidencePlan,
    EvidenceRequest,
    FreshnessStatus,
    GateSummary,
    RetrievalSurface,
    RiskLevel,
    TrustDecision,
    VerifiedContextRequest,
    VerifiedContextResult,
)
from opencontext_core.retrieval.planner import RetrievalPlanner

# --- PR-001 Runtime Core (workflow-neutral substrate), re-exported here ---
from opencontext_core.runtime.api import (
    ApplyResult,
    ArchiveResult,
    ArtifactSummary,
    InspectionReport,
    InspectionScope,
    MutationRequest,
    ReceiptSummary,
    RunRequest,
    RuntimeApi,
    RuntimeEventInput,
    SessionRef,
    SessionState,
    StartSessionRequest,
)
from opencontext_core.runtime.brain import (
    HistoryPort,
    IntelligencePort,
    KnowledgeGraphPort,
    NullRuntimeBrain,
    RuntimeBrain,
    RuntimeBrainPort,
)
from opencontext_core.runtime.decision_log import (
    DecisionLogEntry,
    DecisionRecorder,
    SelectionKind,
    redact_chain_of_thought,
)
from opencontext_core.runtime.decisions import (
    DECISION_CONTRACT_VERSION,
    DECISION_EVENT_FAMILY,
    DecisionKind,
    DecisionLog,
    NextNodeDecision,
    RuntimeDecision,
    SchedulingDecision,
    SimulationReport,
    summarize_decision_log,
)
from opencontext_core.runtime.errors import RuntimeErrorCode, RuntimeFailure
from opencontext_core.runtime.event_bus import (
    CollectingConsumer,
    EventBus,
    EventConsumer,
    JsonlEventBus,
)
from opencontext_core.runtime.events import EventCategory, RuntimeEvent, make_event
from opencontext_core.runtime.execution_strategy import ExecutionStrategy, resolve_strategy
from opencontext_core.runtime.modes import RuntimeMode
from opencontext_core.runtime.run import (
    GateResult,
    NextAction,
    NodeResult,
    RunResult,
    RuntimeRun,
)
from opencontext_core.runtime.scheduler import (
    HarnessScheduler,
    PlanCostEstimator,
    RuntimeScheduler,
    Scheduler,
)
from opencontext_core.runtime.session import (
    ExecutionProfile,
    LiveState,
    RuntimeSession,
    SessionStatus,
)
from opencontext_core.runtime.session_store import SessionStore
from opencontext_core.runtime.state_machine import StateMachine, TransitionDecision
from opencontext_core.runtime.workflow_runner import (
    ExecutionContext,
    NodeSpec,
    WorkflowRunner,
    WorkflowSpec,
)
from opencontext_core.safety.firewall import ContextFirewall
from opencontext_core.safety.trace_sanitizer import TraceSanitizer
from opencontext_core.trace.logger import LocalTraceLogger
from opencontext_core.workflow.engine import WorkflowEngine
from opencontext_core.workflow.steps import WorkflowServices
from opencontext_core.workspace.layout import ensure_workspace


# DEPRECATED(2.0): legacy budget gateway; superseded by providers.gateway.ProviderGateway
# (PR-012, budget-gate parity). Still the live default; remove when runtime.gateway_enabled
# is default + legacy removed (milestone-E).
class BudgetAwareLLMGateway:
    """Wraps an LLMGateway to provide budget-aware routing and tracking."""

    def __init__(
        self,
        base_gateway: LLMGateway,
        router: ModelRoleRouter,
        budget_manager: CallBudgetManager,
        quality_gate: PreLLMQualityGate,
    ) -> None:
        self.base_gateway = base_gateway
        self.router = router
        self.budget_manager = budget_manager
        self.quality_gate = quality_gate

    def generate(self, request: LLMRequest) -> LLMResponse:
        task_complexity = request.metadata.get("task_complexity", "standard")
        role = request.metadata.get("role", "generate")

        route = self.router.route_with_budget(role, task_complexity)

        # Route onto a COPY — never mutate the caller's request. In-place mutation
        # relabels an explicitly-injected gateway and makes retries non-idempotent.
        routed = request.model_copy(update={"provider": route["provider"], "model": route["model"]})

        # This gateway owns the *budget* decision only. Context-size limits are
        # enforced upstream by the planner's token budget, and provider/secret
        # policy by ContextFirewall.check_provider_call — so only budget risks are
        # fatal here (a context-free generation is valid, not a gate failure).
        # A budget swap only ever routes to a LOCAL provider (ollama/lmstudio/…),
        # which adds no external egress beyond what the firewall already approved,
        # so no provider re-check is needed; the local backend is honored by
        # ProviderGateway.generate's re-dispatch on routed.provider.
        gate_report = self.quality_gate.evaluate(
            context_tokens=0,
            max_tokens=1_000_000,
            provider_allowed=True,
            source_count=len(routed.context_items),
            budget_manager=self.budget_manager,
            provider=routed.provider,
            model=routed.model,
        )
        budget_risks = [r for r in gate_report.risks if r.startswith("call_budget")]
        if budget_risks:
            raise WorkflowExecutionError(
                f"Call blocked by budget quality gate: {gate_report.reason} - {budget_risks}"
            )

        self.budget_manager.consume(routed.provider, routed.model)
        return self.base_gateway.generate(routed)


class RuntimeResult(BaseModel):
    """High-level result returned by the runtime facade."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(description="Final answer text.")
    trace_id: str = Field(description="Persisted trace identifier.")
    token_usage: dict[str, int] = Field(description="Trace token usage summary.")
    selected_context_count: int = Field(ge=0, description="Number of selected context items.")


class PreparedContext(BaseModel):
    """Persisted context bundle prepared for a non-CLI adapter."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="User task or retrieval query used to prepare context.")
    trace_id: str = Field(description="Persisted trace identifier for this context bundle.")
    context: str = Field(description="Compact redacted context text for adapter consumption.")
    included_sources: list[str] = Field(description="Sources included in the prepared context.")
    omitted_sources: list[str] = Field(description="Sources omitted from the prepared context.")
    token_usage: dict[str, int] = Field(description="Context and prompt token accounting.")
    trust_decision: dict[str, str] = Field(description="Planner trust decision metadata.")
    fallback_actions: list[str] = Field(
        description="Planner fallback actions for low-trust evidence."
    )
    source_surfaces: list[str] = Field(description="Planner surfaces represented in the evidence.")
    risk_level: str = Field(
        default=RiskLevel.NORMAL.value, description="Risk classification for the query/evidence."
    )
    gates: list[GateSummary] = Field(
        default_factory=list, description="Verification gate results (parity with verify_context)."
    )
    aicx: dict[str, object] | None = Field(
        default=None, description="AICX bytecode compact dict for transport (side-channel)."
    )


class ProjectSetupResult(BaseModel):
    """Result of non-CLI project setup and indexing."""

    model_config = ConfigDict(extra="forbid")

    root: str = Field(description="Project root that was prepared.")
    config_path: str = Field(description="OpenContext YAML configuration path.")
    workspace_path: str = Field(description="Project-local .opencontext workspace path.")
    manifest_path: str = Field(description="Persisted project manifest path.")
    files: int = Field(ge=0, description="Indexed file count.")
    symbols: int = Field(ge=0, description="Indexed symbol count.")
    technology_profiles: list[str] = Field(description="Detected technology profiles.")


class OpenContextRuntime:
    """Facade for project indexing and configured workflow execution."""

    #: Sentinel used to detect when the caller did not pass ``storage_path``.
    _STORAGE_PATH_UNSET: object = object()

    def __init__(
        self,
        config_path: str | Path | None = None,
        config: OpenContextConfig | None = None,
        storage_path: str | Path | object = _STORAGE_PATH_UNSET,
        memory_store: ProjectMemoryStore | None = None,
        llm_gateway: LLMGateway | None = None,
        technology_profiles: list[TechnologyProfile] | None = None,
        embedding_worker: AsyncEmbeddingWorker | None = None,
    ) -> None:
        import logging as _logging

        self.config_path = Path(config_path) if config_path is not None else None
        self.config = config or self._load_config_or_defaults(self.config_path)

        # --- Path resolution (user-dir-storage PR Phase 1) ---
        # Derive the project root from config so the resolver can compute
        # the XDG/LOCALAPPDATA project directory.  Callers that pass an
        # explicit ``storage_path`` retain full backward compatibility — their
        # value wins and the resolver is NOT called.
        _root = Path(self.config.project_index.root)
        # Store root explicitly so subcomponents (e.g. RunReceiptStore) that
        # need the project root can use self.root instead of path math on
        # storage_path — which breaks in user mode because storage_path is
        # under XDG, not the repo.
        self.root: Path = _root.resolve()

        if storage_path is OpenContextRuntime._STORAGE_PATH_UNSET:
            # No explicit override — use the resolver.
            _storage_config = self.config.storage
            self.storage_path = resolve_storage_path(
                _root, _storage_config.mode, _storage_config.custom_path
            )
            self.workspace_path = resolve_workspace_path(
                _root, _storage_config.mode, _storage_config.custom_path
            )
            # Ensure the storage directory exists and write the ownership manifest.
            _manifest_first_write = not self.storage_path.exists()
            self.storage_path.mkdir(parents=True, exist_ok=True)
            try:
                from importlib.metadata import version as _pkg_version

                _oc_version = _pkg_version("opencontext-core")
            except Exception:
                _oc_version = "unknown"
            write_manifest(self.storage_path, _root, _oc_version)
            # Legacy detection — warn if old in-repo state dirs exist.
            _legacy = detect_legacy(_root)
            if _legacy is not None:
                _legacy_paths = [
                    str(p)
                    for p in [_legacy.storage_path, _legacy.workspace_path]
                    if p is not None
                ]
                _legacy_str = " and ".join(_legacy_paths)
                warnings.warn(
                    f"legacy local state detected at {_legacy_str}; "
                    "run `opencontext storage migrate` to move it",
                    stacklevel=2,
                )
                _logging.getLogger("opencontext").warning(
                    "legacy local state detected at %s; "
                    "run `opencontext storage migrate` to move it",
                    _legacy_str,
                )
        else:
            # Explicit storage_path passed — backward-compat path; resolver skipped.
            self.storage_path = Path(storage_path)  # type: ignore[arg-type]
            self.workspace_path = _root / ".opencontext"
        self.memory_store = memory_store or LocalProjectMemoryStore(self.storage_path)
        # Parsed-manifest cache (stat-signature keyed). Parsing the whole-repo
        # manifest JSON through Pydantic is query-independent and was repeated on
        # every prepare_context / verify_context call (and 3x per benchmark case),
        # which dominated warm retrieval latency. The cache is invalidated
        # automatically whenever index_project rewrites the manifest, because the
        # file's (mtime_ns, size) signature changes — so correctness is unchanged.
        self._manifest_cache: ProjectManifest | None = None
        self._manifest_cache_sig: tuple[int, int] | None = None
        self.trace_logger = LocalTraceLogger(self.storage_path / "traces")
        self.llm_gateway = llm_gateway or self._gateway_from_config()
        self.technology_profiles = technology_profiles
        self.tunnel_store = GraphTunnelStore(self.storage_path)
        self.knowledge_graph = KnowledgeGraph(db_path=self.storage_path / "context_graph.db")
        # Self-improvement gate (config.learning.enabled, default True). When
        # disabled we install a no-op stand-in so every in-loop ``self.learning.*``
        # call-site keeps working without a per-call guard (DR2). Default True
        # preserves today's behavior byte-for-byte.
        self.learning: LearningOrchestrator | NullLearningOrchestrator
        if self.config.learning.enabled:
            self.learning = LearningOrchestrator(
                storage_path=self.storage_path / "learning",
                kg_db_path=self.storage_path / "context_graph.db",
                default_token_budget=self.config.context.max_input_tokens,
            )
        else:
            self.learning = NullLearningOrchestrator()
        self.compression_engine = CompressionEngine(self.config.context.compression)
        vector_store = (
            LocalVectorStore(self.storage_path)
            if self.config.embedding.enabled
            else NullVectorStore()
        )
        self.embedding_worker = embedding_worker or create_worker(
            self.config, vector_store=vector_store
        )
        if self.embedding_worker and self.config.embedding.enabled:
            self.embedding_worker.start()

        # Initialize call budget and routing
        self.free_registry = FreeProviderRegistry()
        self.budget_manager = CallBudgetManager()

        # Map roles from config to router format. models.default is the source of
        # truth for the primary 'generate' role and MUST win over the
        # models.roles 'generate' entry — which defaults to mock, so otherwise a
        # user who sets models.default (e.g. ollama/qwen) never generates with it
        # and every call is forced onto mock-llm.
        router_roles = {}
        for role, pconfig in self.config.models.roles.items():
            router_roles[role] = {
                "provider": pconfig.provider,
                "model": pconfig.model,
            }
        if self.config.models.default:
            router_roles["generate"] = {
                "provider": self.config.models.default.provider,
                "model": self.config.models.default.model,
            }

        self.router = ModelRoleRouter(
            roles=router_roles,
            budget_manager=self.budget_manager,
            free_registry=self.free_registry,
            strategy=self.config.providers.strategy,
        )
        self.quality_gate = PreLLMQualityGate()

        # PR-012: route provider calls through the unified ProviderGateway facade
        # when runtime.gateway_enabled (default off). The facade composes routing
        # -> policy -> prompt -> adapter with bounded fallback, a cost ledger,
        # provider events/receipts, and a Decision Log record per choice. Off, the
        # legacy BudgetAwareLLMGateway path runs byte-for-byte as before.
        raw_gateway = self.llm_gateway
        if self.config.runtime.gateway_enabled:
            from opencontext_core.cache.provider_cache import ProviderResponseCache
            from opencontext_core.cache.store import CcrBackedCacheStore
            from opencontext_core.learning.feed import record_outcome

            self.cost_ledger = CostLedger()
            # RunReceiptStore appends ``.opencontext/receipts`` to its root.
            # Use self.root (the project root) directly so the path is correct
            # in both local mode (where storage_path is <root>/.storage/opencontext)
            # and user mode (where storage_path is in XDG and .parent.parent would
            # point to the wrong XDG ancestor directory).
            self.provider_receipts = RunReceiptStore(self.root)
            self.provider_decisions = DecisionRecorder()
            self.provider_events = ProviderEventEmitter()
            # PR-000.3 provider-response cache seam, plugged in but conservative
            # (enabled=False) so response caching never silently changes the
            # agentic loop; flip `enabled` to reuse identical provider responses.
            self.provider_cache = ProviderResponseCache(CcrBackedCacheStore(), enabled=False)
            self.llm_gateway = UnifiedProviderGateway(
                raw_gateway,
                router=self.router,
                firewall=ContextFirewall(self.config),
                budget_manager=self.budget_manager,
                quality_gate=self.quality_gate,
                ledger=self.cost_ledger,
                receipts=self.provider_receipts,
                recorder=self.provider_decisions,
                emitter=self.provider_events,
                cache=self.provider_cache,
                learning=self.learning,
                feed=record_outcome,
                retry_limit=self.config.providers.retry_limit,
                fallback=self.config.providers.fallback,
            )
        else:
            # Wrap gateway with budget awareness (legacy path).
            self.llm_gateway = BudgetAwareLLMGateway(
                base_gateway=raw_gateway,
                router=self.router,
                budget_manager=self.budget_manager,
                quality_gate=self.quality_gate,
            )

        # PR-011: Runtime Intelligence advisory seam. The live RuntimeScheduler
        # CONSULTS the RI cost model (SchedulerPlanEstimator) inside simulate()
        # when runtime_intelligence_enabled (Scheduler -> Runtime Intelligence ->
        # workflow forecast); off, simulate() returns the typed stub forecast and
        # the path is byte-for-byte unchanged. RI is advisory only — the
        # StateMachine inside the scheduler still governs every transition
        # (RB-007/§23.1: it recommends, never overrides).
        # NOTE: no production RuntimeScheduler execution root drives decide_next
        # yet — simulate() is the sole live consumer of the estimator; the typed
        # PlanCostEstimator seam stays stable either way.
        estimator: PlanCostEstimator | None = None
        if self.config.runtime_intelligence_enabled:
            from opencontext_core.runtime_intelligence.simulator import (
                SchedulerPlanEstimator,
            )

            estimator = SchedulerPlanEstimator()
        self.runtime_scheduler = RuntimeScheduler(RuntimeBrain(), estimator=estimator)

        self._validate_security_mode_guards()

        # Check context-first mode
        from opencontext_core.user_prefs import UserConfigStore

        store = UserConfigStore()
        prefs = store.load()
        if prefs.context_first_mode:
            self._agent_subsystems_disabled = True
            import logging as _logging

            _logging.getLogger("opencontext").info(
                "Context-first mode active — agent subsystems disabled."
            )
        else:
            self._agent_subsystems_disabled = False

        # v2: contract-driven planning (additive — never raises to caller)
        try:
            from opencontext_core.backends.factory import BackendFactory
            from opencontext_core.context.planning.classifier import TaskClassifier
            from opencontext_core.context.planning.contract import ContextContractBuilder
            from opencontext_core.context.planning.planner import ContextPlanner
            from opencontext_core.context.planning.risk import RiskClassifier

            self._task_classifier = TaskClassifier()
            self._risk_classifier = RiskClassifier()
            self._contract_builder = ContextContractBuilder(
                classifier=self._task_classifier,
                risk_classifier=self._risk_classifier,
            )
            self._context_planner = ContextPlanner(
                graph=self.knowledge_graph if hasattr(self, "knowledge_graph") else None,
            )
            _v2_storage = self.storage_path
            # Use the real config so the factory resolves a working AgentMemoryStore
            # (memory.provider) instead of degrading to Null on a mismatched shape.
            self._v2_memory_store = BackendFactory.create_memory_store(self.config, _v2_storage)
            self._v2_enabled = True
        except Exception:
            self._v2_enabled = False

    def build_contract(self, query: str) -> object | None:
        """Build a verified context contract for a query.

        Returns a ContextContract if v2 planning is available, else None.
        Never raises — callers can always treat None as "v2 not available".
        """
        if not getattr(self, "_v2_enabled", False):
            return None
        try:
            return self._contract_builder.build(query)
        except Exception:
            return None

    def reindex_files(
        self, changed_paths: set[str], root: str | Path | None = None
    ) -> dict[str, int]:
        """Incrementally re-index only the changed files.

        Called by the watch service after a debounce window. Falls back to a
        full index_project() when the knowledge graph is not configured.
        """
        if not self.config.project_index.enabled:
            raise ConfigurationError("Project indexing is disabled by configuration.")
        project_root = Path(root) if root is not None else Path(self.config.project_index.root)
        return self.knowledge_graph.reindex_files(changed_paths, project_root)

    def index_project(self, root: str | Path | None = None) -> ProjectManifest:
        """Index a project and persist the project manifest."""

        if not self.config.project_index.enabled:
            raise ConfigurationError("Project indexing is disabled by configuration.")

        op_id = self.learning.start_operation("index", str(root) if root else ".")
        indexer = ProjectIndexer(
            self.config.project_index,
            self.config.project.name,
            profiles=self.technology_profiles,
            knowledge_graph=self.knowledge_graph,
        )
        manifest = indexer.build_manifest(Path(root) if root is not None else None)
        self.memory_store.save_manifest(manifest)
        # Invalidate the parsed-manifest cache so the next load_manifest re-reads the
        # PERSISTED (redacted) manifest from disk — never the un-redacted in-memory
        # object, which would leak sensitive summaries past redaction. (The disk-read
        # cache in load_manifest, keyed by the file signature, stays safe.)
        self._manifest_cache = None
        self._manifest_cache_sig = None

        # Index non-code context artifacts (schemas, specs, ADRs) defined in config
        artifacts = self.config.project_index.context_artifacts
        if artifacts and self.knowledge_graph:
            from opencontext_core.indexing.artifact_indexer import index_artifacts

            project_root = Path(root).resolve() if root else Path.cwd()
            index_artifacts(
                artifacts, project_root, self.knowledge_graph.db, self.config.project.name
            )

        # Async enqueue embeddings if worker enabled
        if self.config.embedding.enabled and self.embedding_worker:
            items = items_from_manifest(manifest)
            # Reconcile the vector store to the freshly-scanned file set BEFORE
            # enqueueing the new generation: drop vectors for files no longer scanned
            # (since-deleted, or a vendored tree now ignored such as a venv) so they
            # stop surfacing as semantic retrieval evidence. Same orphaning bug as the
            # KG — enqueue only ever added; it never removed. Pruning first means the
            # prune touches only the prior generation and the async worker appends the
            # fresh one without racing the rewrite. Best-effort: never fails indexing.
            store = getattr(self.embedding_worker, "vector_store", None)
            if store is not None and items:
                try:
                    kept_paths = {file.path for file in manifest.files}
                    pruned_vectors = store.prune_absent_sources(
                        kept_paths, self.config.project.name
                    )
                    if pruned_vectors:
                        import logging as _logging

                        _logging.getLogger("opencontext").info(
                            "vector store: pruned %d stale embedding(s)", pruned_vectors
                        )
                except Exception as exc:
                    import logging as _logging

                    _logging.getLogger("opencontext").warning(
                        "vector store reconciliation failed: %s", exc
                    )
            if items:
                self.embedding_worker.enqueue_sync(items)

        kg_stats = manifest.metadata.get("knowledge_graph", {})
        # problem 3: index succeeds when manifest was written. ACON-lite uses the
        # ``success`` boolean to widen budget on ops that failed while context was
        # dropped; indexing never drops items, but never passing success left it NULL
        # in SQLite and disabled the learning subsystem's feedback path entirely.
        self.learning.finish_operation(
            op_id,
            tokens_used=sum(f.tokens for f in manifest.files),
            files_consulted=len(manifest.files),
            symbols_consulted=len(manifest.symbols),
            success=True,
            metadata={
                "kg_files_indexed": kg_stats.get("files_indexed", 0),
                "kg_nodes": kg_stats.get("nodes", 0),
            },
        )

        # problem 13: distill accumulated operation metrics into optimized budgets at
        # index cadence (infrequent, always reached on the live path) so ACON-lite's
        # learned budgets actually refresh — previously only `opencontext verify` ever
        # triggered optimize_budgets(), so the feedback loop never closed in normal use.
        optimizer = getattr(self.learning, "optimizer", None)
        if optimizer is not None:
            try:
                optimizer.optimize_budgets()
            except Exception:
                pass  # budget optimization is best-effort, never block indexing

        return manifest

    def setup_project(
        self,
        root: str | Path = ".",
        *,
        write_config: bool = True,
        refresh_index: bool = True,
    ) -> ProjectSetupResult:
        """Create the non-CLI workspace harness and persist a project index."""

        project_root = Path(root).resolve()
        ensure_workspace(project_root)
        config_path = project_root / "opencontext.yaml"
        if write_config and not config_path.exists():
            config_path.write_text(
                yaml.safe_dump(self.config.model_dump(mode="json"), sort_keys=False),
                encoding="utf-8",
            )
        manifest = self.index_project(project_root) if refresh_index else self.load_manifest()
        return ProjectSetupResult(
            root=str(project_root),
            config_path=str(config_path),
            workspace_path=str(project_root / ".opencontext"),
            manifest_path=str(self.storage_path / "project_manifest.json"),
            files=len(manifest.files),
            symbols=len(manifest.symbols),
            technology_profiles=manifest.technology_profiles,
        )

    def ask(self, question: str, workflow_name: str = "code_assistant") -> RuntimeResult:
        """Run a configured workflow for a user question."""

        optimized_budget = self.learning.get_optimized_budget(
            "ask", fallback=self.config.context.max_input_tokens
        )
        op_id = self.learning.start_operation(
            "ask", question, task_type=workflow_name, tokens_budgeted=optimized_budget
        )
        services = WorkflowServices(
            config=self.config,
            memory_store=self.memory_store,
            trace_logger=self.trace_logger,
            llm_gateway=self.llm_gateway,
            embedding_worker=self.embedding_worker,
            tunnel_store=self.tunnel_store,
        )
        engine = WorkflowEngine(self.config, services)
        state = engine.run(workflow_name, question)
        if state.trace is None:
            self.learning.finish_operation(op_id, success=False)
            raise WorkflowExecutionError("Workflow completed without a trace.")
        llm_response_content = state.llm_response.content if state.llm_response else ""
        token_usage = state.trace.token_estimates
        total_tokens = sum(token_usage.values()) if token_usage else 0
        self.learning.finish_operation(
            op_id,
            tokens_used=total_tokens,
            context_items_selected=len(state.trace.selected_context_items),
            # Co-record omissions with the outcome so ACON-lite can widen the budget
            # for an op type that fails while context was dropped (token_optimizer).
            context_items_omitted=len(getattr(state, "discarded_context", []) or []),
            success=True,
            metadata={"workflow": workflow_name, "answer_length": len(llm_response_content)},
        )
        return RuntimeResult(
            answer=llm_response_content,
            trace_id=state.trace.run_id,
            token_usage=token_usage,
            selected_context_count=len(state.trace.selected_context_items),
        )

    def load_manifest(self) -> ProjectManifest:
        """Load the persisted project manifest, caching the parse across calls.

        Parsing the whole-repo manifest JSON through Pydantic is the dominant
        per-query cost on large repos and is entirely query-independent, so it is
        memoized on the runtime keyed by the manifest file's ``(mtime_ns, size)``
        signature. The cache is transparent: any write (``index_project`` ->
        ``save_manifest``) changes the signature and forces a re-parse, so callers
        always observe the on-disk manifest exactly as before — only the redundant
        re-parses are elided. Stores without a stat-able ``manifest_path``
        (in-memory/custom) bypass the cache and load as before.
        """

        manifest_path = getattr(self.memory_store, "manifest_path", None)
        if manifest_path is None:
            return self.memory_store.load_manifest()
        try:
            stat = Path(manifest_path).stat()
            signature = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            # The file is missing/unreadable: defer to the store so it raises the
            # canonical MemoryStoreError (e.g. "run `opencontext index .` first").
            self._manifest_cache = None
            self._manifest_cache_sig = None
            return self.memory_store.load_manifest()
        if self._manifest_cache is not None and self._manifest_cache_sig == signature:
            return self._manifest_cache
        manifest = self.memory_store.load_manifest()
        self._manifest_cache = manifest
        self._manifest_cache_sig = signature
        return manifest

    def _seed_manifest_cache(self, manifest: ProjectManifest) -> None:
        """Cache a just-written manifest keyed to its on-disk stat signature.

        Best-effort: if the store has no stat-able ``manifest_path`` (in-memory /
        custom), the cache is simply left empty and ``load_manifest`` falls back to
        the store. A stat failure here never blocks indexing.
        """

        manifest_path = getattr(self.memory_store, "manifest_path", None)
        if manifest_path is None:
            return
        try:
            stat = Path(manifest_path).stat()
        except OSError:
            self._manifest_cache = None
            self._manifest_cache_sig = None
            return
        self._manifest_cache = manifest
        self._manifest_cache_sig = (stat.st_mtime_ns, stat.st_size)

    def render_repo_map(self, query: str | None = None, max_tokens: int | None = None) -> str:
        """Render a compact repository map from the persisted manifest."""

        manifest = self.load_manifest()
        engine = RepoMapEngine()
        repo_map = engine.build(manifest, query)
        return engine.render(repo_map, max_tokens or self.config.repo_map.max_tokens)

    def build_context_pack(
        self,
        query: str,
        max_tokens: int | None = None,
        surface: RetrievalSurface = RetrievalSurface.RUNTIME,
    ) -> ContextPackResult:
        """Build a token-aware context pack from retrieved project context."""

        pack, _trace_id = self.build_context_pack_with_trace(query, max_tokens, surface=surface)
        return pack

    def build_context_pack_with_trace(
        self,
        query: str,
        max_tokens: int | None = None,
        surface: RetrievalSurface = RetrievalSurface.RUNTIME,
    ) -> tuple[ContextPackResult, str]:
        """Build a context pack and return it with the id of the persisted trace.

        The trace is always persisted by ``_build_context_pack_with_trace``; this
        surfaces its id so callers (e.g. the harness explore phase) can record the
        run's retrieval provenance instead of discarding it.
        """

        # Use optimized budget if no explicit max_tokens provided
        if max_tokens is None:
            max_tokens = self.learning.get_optimized_budget(
                "context_pack", fallback=self.config.context.max_input_tokens
            )
        budget = max_tokens
        op_id = self.learning.start_operation("context_pack", query, tokens_budgeted=budget)
        pack, trace, _plan = self._build_context_pack_with_trace(query, max_tokens, surface=surface)
        total_tokens = sum(trace.token_estimates.values()) if trace.token_estimates else 0
        # problem 3 + 11: record the *real* context_items_omitted count AND a
        # computed success flag. ACON-lite's TokenOptimizer widens the budget for
        # op types that fail while dropping context (``success is False AND
        # context_items_omitted > 0``). A context_pack "fails" — in the sense of
        # needing a wider budget — exactly when it could not fit everything, so
        # success must be FALSE on any omission/overflow. Passing a constant
        # success=True (the earlier fix) left the feedback path dead because the
        # ``success is False`` branch never fired.
        pack_fit = pack.used_tokens <= budget and len(pack.omitted) == 0
        self.learning.finish_operation(
            op_id,
            tokens_used=total_tokens,
            context_items_selected=len(pack.included),
            context_items_omitted=len(pack.omitted),
            success=pack_fit,
            metadata={"max_tokens": budget, "pack_tokens": pack.used_tokens},
        )
        return pack, trace.run_id

    def prepare_context(
        self,
        query: str,
        root: str | Path | None = None,
        max_tokens: int | None = None,
        refresh_index: bool = False,
        surface: RetrievalSurface = RetrievalSurface.API,
    ) -> PreparedContext:
        """Prepare, persist, and return a compact context bundle for API adapters."""

        if refresh_index:
            self.index_project(root)
        else:
            try:
                self.load_manifest()
            except MemoryStoreError:
                self.index_project(root)

        pack, trace, plan = self._build_context_pack_with_trace(query, max_tokens, surface=surface)
        risk_level = _classify_context_risk(query, evidence_count=len(plan.evidence))
        gates = _verified_context_gates(
            list(plan.evidence), pack.used_tokens, max_tokens, plan, risk_level
        )
        aicx = None
        try:
            from opencontext_core.context.bytecode import AICXCompiler, AICXRenderer

            aicx = AICXRenderer().render_compact(AICXCompiler().compile(plan))
        except Exception as exc:  # AICX is an optional side-channel — never block.
            import logging

            logging.getLogger("opencontext").warning("AICX side-channel failed: %s", exc)
        return PreparedContext(
            query=query,
            trace_id=trace.run_id,
            context=self._render_adapter_context(pack),
            included_sources=[item.source for item in pack.included],
            omitted_sources=[item.source for item in pack.omitted],
            token_usage=trace.token_estimates,
            trust_decision=plan.trust_decision.model_dump(mode="json"),
            fallback_actions=plan.fallback_actions,
            source_surfaces=[surface.value for surface in plan.source_surfaces],
            risk_level=risk_level.value,
            gates=gates,
            aicx=aicx,
        )

    def _compile_aicx_for_transport(
        self, plan: EvidencePlan
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        """Compile AICX bytecode for transport, plus a cross-turn delta.

        Returns ``(compact, delta)``. The delta diffs against the project's
        previous bytecode (cache por proyecto) so unchanged evidence is not
        re-sent; the new bytecode is persisted as the next base. Entirely
        best-effort: AICX is an optional side-channel, so any failure yields
        ``(compact_or_None, None)`` and never blocks verification.
        """
        try:
            from opencontext_core.context.bytecode import AICXCompiler, AICXRenderer

            bc = AICXCompiler().compile(plan)
        except Exception:
            return None, None
        compact = AICXRenderer().render_compact(bc)
        delta: dict[str, object] | None = None
        try:
            from opencontext_core.context.bytecode.delta import diff_bytecode
            from opencontext_core.context.bytecode.session_cache import (
                load_last_bytecode,
                save_last_bytecode,
            )

            prev = load_last_bytecode(self.storage_path)
            if prev is not None:
                delta = diff_bytecode(prev, bc).model_dump(mode="json")
            save_last_bytecode(self.storage_path, bc)
        except Exception:
            delta = None
        return compact, delta

    def verify_context(self, request: VerifiedContextRequest) -> VerifiedContextResult:
        """Build one-shot verified context with local evidence, gates, risk, and trace."""

        risk_level = _classify_context_risk(request.query, evidence_count=0)
        omitted_sources: list[str] = []
        if not request.include_vector or not self.config.embedding.enabled:
            omitted_sources.append("vector_disabled")
        if not request.include_memory:
            omitted_sources.append("memory_disabled")

        if request.refresh_index:
            self.index_project(request.root)

        try:
            pack, trace, plan = self._build_context_pack_with_trace(
                request.query,
                request.max_tokens,
                surface=RetrievalSurface.RUNTIME,
                risk_level=risk_level,
            )
        except MemoryStoreError:
            plan = EvidencePlan(
                request=EvidenceRequest(
                    query=request.query,
                    root=request.root or Path(self.config.project_index.root),
                    surface=RetrievalSurface.RUNTIME,
                    max_tokens=request.max_tokens or self.config.context.sections.retrieved_context,
                    risk_level=RiskLevel.HIGH.value,
                ),
                evidence=[],
                fallback_actions=["index_project"],
                trust_decision=TrustDecision(
                    status="insufficient",
                    reason="no local manifest available",
                ),
                trace_id=uuid4().hex,
                omissions=["manifest_unavailable"],
                source_surfaces=[RetrievalSurface.RUNTIME],
            )
            trace_id = self._persist_insufficient_trace(
                request.query, plan, [*omitted_sources, *plan.omissions]
            )
            return VerifiedContextResult(
                trace_id=trace_id,
                context="",
                evidence=[],
                memory=[],
                gates=_verified_context_gates([], 0, request.max_tokens, plan, RiskLevel.HIGH),
                risk_level=RiskLevel.HIGH,
                trust_decision=plan.trust_decision,
                token_usage={"final_context_pack": 0},
                omitted_sources=[*omitted_sources, *plan.omissions],
            )

        risk_level = _classify_context_risk(request.query, evidence_count=len(plan.evidence))
        # The pack was retrieved with a provisional risk (computed before any
        # evidence existed). Recompute the trust decision with the evidence-aware
        # risk so the policy gate is consistent with the risk we report — otherwise
        # a normal-risk query could fail the policy gate citing "high-risk".
        from opencontext_core.retrieval.planner import _trust_decision

        plan.trust_decision = _trust_decision(
            plan.request.model_copy(update={"risk_level": risk_level.value}),
            list(plan.evidence),
            list(plan.fallback_actions),
        )
        memory = self._load_verified_memory(request) if request.include_memory else []
        gates = _verified_context_gates(
            [*plan.evidence, *memory],
            pack.used_tokens,
            request.max_tokens,
            plan,
            risk_level,
        )
        trust_decision = plan.trust_decision
        if any(not gate.passed for gate in gates):
            trust_decision = TrustDecision(status="insufficient", reason="verification gate failed")

        # Enforce hard gates: never SERVE context that violates policy or lacks
        # provenance. Soft-gate failures (coverage/freshness/budget) still serve a
        # degraded-but-clean pack; the trust decision flags it either way.
        rendered_context = self._render_adapter_context(pack)
        hard_failures = [
            gate.name for gate in gates if not gate.passed and gate.name in ("policy", "provenance")
        ]
        if hard_failures:
            rendered_context = ""
            trust_decision = TrustDecision(
                status="insufficient",
                reason=f"context withheld: {', '.join(hard_failures)} gate failed",
            )

        _aicx_compact, _aicx_delta = self._compile_aicx_for_transport(plan)

        # Auto-improvement feed (non-blocking): record this verification's outcome so
        # the learning subsystem can observe gate failures / token spend. A learning
        # failure never changes the gate/trust result.
        from opencontext_core.learning.feed import record_outcome

        record_outcome(
            self.learning,
            operation_type="verify_context",
            query=request.query,
            tokens_used=pack.used_tokens,
            tokens_budgeted=request.max_tokens or self.config.context.sections.retrieved_context,
            context_items_selected=len(plan.evidence),
            context_items_omitted=len(plan.omissions),
            success=all(gate.passed for gate in gates),
            failing_gates=[gate.name for gate in gates if not gate.passed],
        )

        return VerifiedContextResult(
            trace_id=trace.run_id,
            context=rendered_context,
            evidence=plan.evidence,
            memory=memory,
            gates=gates,
            risk_level=risk_level,
            trust_decision=trust_decision,
            token_usage=trace.token_estimates,
            omitted_sources=[*omitted_sources, *plan.omissions],
            aicx=_aicx_compact,
            aicx_delta=_aicx_delta,
        )

    def _load_verified_memory(self, request: VerifiedContextRequest) -> list[EvidenceItem]:
        root = request.root or Path(self.config.project_index.root)
        # Source of truth first: the canonical SQLite AgentMemoryStore (cognitive
        # layers, decay, reinforce, supersede). The markdown ContextRepository is a
        # secondary human-readable layer — added only for items the canonical store
        # does not already have, so the two can never diverge in recall.
        items: list[EvidenceItem] = self._load_agent_memory_evidence(request.query, exclude=set())
        seen = {i.id for i in items}
        for item in ContextRepository(root).search(request.query)[:3]:
            ev_id = f"memory:{item.id}"
            if ev_id in seen:
                continue
            seen.add(ev_id)
            items.append(
                EvidenceItem(
                    id=ev_id,
                    content=item.content,
                    source=item.source,
                    source_type="memory",
                    provenance={"source": item.source, "kind": item.kind, "memory_id": item.id},
                    confidence=0.8,
                    freshness=FreshnessStatus.CURRENT,
                    surface=RetrievalSurface.RUNTIME,
                    tokens=item.tokens,
                    protected=item.pin,
                    classification=item.classification,
                )
            )
        return items

    def _load_agent_memory_evidence(self, query: str, *, exclude: set[str]) -> list[EvidenceItem]:
        store = getattr(self, "_v2_memory_store", None)
        if store is None:
            return []
        from opencontext_core.models.context import DataClassification

        out: list[EvidenceItem] = []
        try:
            for rec in store.search(query, limit=3):
                ev_id = f"memory:{rec.id}"
                if ev_id in exclude:
                    continue
                out.append(
                    EvidenceItem(
                        id=ev_id,
                        content=rec.content,
                        source=rec.key,
                        source_type="memory",
                        provenance={
                            "source": rec.key,
                            "kind": rec.layer.value,
                            "memory_id": rec.id,
                            "agent_memory": True,
                        },
                        confidence=rec.confidence,
                        freshness=FreshnessStatus.CURRENT,
                        surface=RetrievalSurface.RUNTIME,
                        tokens=estimate_tokens(rec.content),
                        protected=False,
                        classification=DataClassification.INTERNAL,
                    )
                )
        except Exception as exc:  # canonical memory is best-effort; never block.
            import logging

            logging.getLogger("opencontext").warning("agent memory read failed: %s", exc)
        return out

    def _persist_insufficient_trace(
        self, query: str, plan: EvidencePlan, omitted: list[str]
    ) -> str:
        """Persist a minimal loadable trace for the insufficient/no-manifest path.

        Without this, verify_context returned a trace_id that pointed at no file,
        so load_trace / the API trace route raised 'Trace not found' exactly when
        context was withheld. The returned id (== run_id) resolves via load_trace.
        """

        now = datetime.now(tz=UTC)
        budget = TokenBudgetManager(self.config.context).calculate()
        trace = RuntimeTrace(
            run_id=plan.trace_id,
            trace_id=plan.trace_id,
            name="context_pack.insufficient",
            start_time=now,
            end_time=now,
            workflow_name="context_pack.local",
            input=query,
            provider="local-only",
            model="none",
            selected_context_items=[],
            discarded_context_items=[],
            token_budget=budget,
            token_estimates={"final_context_pack": 0},
            compression_strategy=self.config.context.compression.strategy.value,
            prompt_sections=[],
            final_answer="[INSUFFICIENT_CONTEXT]",
            errors=list(plan.omissions),
            created_at=now,
            metadata={
                "local_only": True,
                "trust_decision": plan.trust_decision.model_dump(mode="json"),
                "omitted_sources": list(omitted),
            },
        )
        sanitized = TraceSanitizer().sanitize(trace, self.config.security.mode)
        ContextFirewall(self.config).check_trace_persistence(sanitized).raise_if_blocked()
        self.trace_logger.persist(sanitized)
        return sanitized.run_id

    def _build_context_pack_with_trace(
        self,
        query: str,
        max_tokens: int | None = None,
        *,
        surface: RetrievalSurface = RetrievalSurface.RUNTIME,
        risk_level: RiskLevel = RiskLevel.NORMAL,
    ) -> tuple[ContextPackResult, RuntimeTrace, EvidencePlan]:
        """Build and persist a context pack, returning the trace that records it."""

        manifest = self.load_manifest()
        # from_config lights up FTS + (config-gated) vector + memory-aware ranking;
        # with defaults it is identical to the bare manifest+graph planner.
        planner = RetrievalPlanner.from_config(
            manifest,
            self.config,
            storage_path=self.storage_path,
            memory_store=getattr(self, "_v2_memory_store", None),
        )
        plan = planner.plan(
            EvidenceRequest(
                query=query,
                root=Path(manifest.root),
                surface=surface,
                max_tokens=max_tokens or self.config.context.sections.retrieved_context,
                risk_level=risk_level.value,
            ),
            self.config.retrieval.top_k,
        )
        # AICX side-channel: compile → validate → (roundtrip check) for the persisted
        # checksum and transport metrics only. It MUST NOT mutate `plan`: the populated
        # planner plan flows on to ContextCompiler so the agent receives real content.
        _bytecode = None
        _bytecode_report = None
        _bytecode_metrics = None
        try:
            from opencontext_core.context.bytecode import (
                AICXCompiler,
                AICXDecoder,
                AICXValidator,
                compute_metrics,
            )

            _bc = AICXCompiler().compile(plan)
            _bytecode_report = AICXValidator().validate(_bc)
            if _bytecode_report.passed:
                import time as _time

                _t0 = _time.monotonic()
                _decoded = AICXDecoder().decode(_bc)  # roundtrip check only — discarded
                _decode_ms = (_time.monotonic() - _t0) * 1000
                _bytecode_metrics = compute_metrics(
                    plan,
                    _bc,
                    decode_time_ms=_decode_ms,
                    roundtrip_loss=len(_decoded.evidence) != len(plan.evidence),
                )
                _bytecode = _bc
        except Exception as exc:  # AICX is optional — never block the main pipeline
            import logging

            logging.getLogger("opencontext").warning("AICX side-channel failed: %s", exc)

        # Evidence carries the planner's hybrid order; the trace records it as the
        # ranked candidate set (the compiler preserves this order into the pack).
        candidates = [evidence_to_context_item(item) for item in plan.evidence]
        ranked = candidates
        sanitized_pack = ContextCompiler().compile(plan, compression_engine=self.compression_engine)
        ContextFirewall(self.config).check_context_export(
            [*sanitized_pack.included, *sanitized_pack.omitted],
            sink="context_pack",
        ).raise_if_blocked()
        trace = self._persist_local_context_pack_trace(
            query,
            manifest,
            candidates,
            ranked,
            sanitized_pack,
            plan,
            aicx_checksum=_bytecode.checksum if _bytecode is not None else None,
            aicx_metrics=_bytecode_metrics.model_dump(mode="json")
            if _bytecode_metrics is not None
            else None,
        )
        return sanitized_pack, trace, plan

    def load_trace(self, trace_id: str) -> RuntimeTrace:
        """Load a trace by identifier."""

        return self.trace_logger.load(trace_id)

    def latest_trace(self) -> RuntimeTrace:
        """Load the latest persisted trace."""

        return self.trace_logger.latest()

    def _gateway_from_config(self) -> LLMGateway:
        model_config = self.config.models.default
        air_gapped = self.config.security.mode is SecurityMode.AIR_GAPPED
        # Prefer the host agent's selected model via MCP sampling when available —
        # zero provider config needed. Forbidden in air-gapped mode (external).
        if not air_gapped:
            from opencontext_core.llm.sampling_gateway import (
                SamplingGateway,
                get_host_sampler,
            )

            sampler = get_host_sampler()
            if sampler is not None:
                return SamplingGateway(sampler, model=model_config.model)
        if model_config.provider == "mock":
            return MockLLMGateway()
        # Air-gapped mode must never reach an external provider — but it must also
        # not crash purely-local commands. index/context/explain/pack build the
        # runtime (and thus a gateway) yet never call out to a model, so raising
        # here broke offline use of the very features air-gapped exists to protect.
        # Degrade to the LOCAL mock gateway with a loud warning instead — the same
        # way an unknown provider is handled just below. Mock never reaches an
        # external provider, so the air-gapped guarantee still holds; an actual
        # generation attempt simply gets mock output it can act on, not a crash.
        if air_gapped:
            warnings.warn(
                "air_gapped mode: no external LLM provider — using the local mock "
                "gateway. Local features (index, context, explain, pack) work; for "
                "real generation, configure a local model such as ollama.",
                stacklevel=2,
            )
            return MockLLMGateway()
        from opencontext_core.llm.provider_gateway import build_provider_gateway

        gateway = build_provider_gateway(model_config.provider, model_config.model)
        if gateway is None:
            # An unknown provider (e.g. a detected google/mistral key with no
            # adapter yet) must not crash every runtime construction. Degrade to
            # the mock gateway with a loud warning so indexing/context still work.
            warnings.warn(
                f"No LLM gateway for provider {model_config.provider!r}; falling "
                "back to the mock gateway. Configure a supported provider "
                "(anthropic, openai, openrouter, ollama) for real generation.",
                stacklevel=2,
            )
            return MockLLMGateway()
        return gateway

    def _load_config_or_defaults(self, config_path: Path | None) -> OpenContextConfig:
        if config_path is not None:
            return load_config(config_path)
        default_path = Path("configs/opencontext.yaml")
        if default_path.exists():
            return load_config(default_path)
        return OpenContextConfig.model_validate(default_config_data())

    def _validate_security_mode_guards(self) -> None:
        if self.config.security.mode is not SecurityMode.AIR_GAPPED:
            return
        if self.config.observability.opentelemetry.enabled:
            raise ConfigurationError("air_gapped mode forbids external telemetry exporters.")
        if self.config.tools.mcp.enabled:
            raise ConfigurationError("air_gapped mode forbids MCP tool adapters.")
        if self.config.security.external_providers_enabled:
            raise ConfigurationError("air_gapped mode forbids external providers.")

    def _recall_memory_for_prompt(self, query: str, project_root: Path) -> str:
        """Recall pinned/relevant project memory and render it for prompt injection.

        Wires ProgressiveDisclosureMemory (it was never called, so harvested
        session memory never re-entered the context pack). Classification-bounded
        and best-effort — any failure or empty repository yields no memory section
        rather than blocking the pack.
        """

        try:
            from opencontext_core.memory_usability.context_repository import ContextRepository
            from opencontext_core.memory_usability.progressive_memory import (
                ProgressiveDisclosureMemory,
            )

            repo = ContextRepository(project_root)
            # Over-fetch candidates, then compress to the recall budget: more
            # signal fits the same prompt tokens. Compression uses the cheap
            # summarize role when a model is bound, else a deterministic trim.
            target = 1000
            plan = ProgressiveDisclosureMemory(repo).select(query, max_tokens=target * 3)
            rendered = "\n".join(f"- {item.content}" for item in plan.included)
            from opencontext_core.memory.rehydration import summarize_to_budget

            return summarize_to_budget(rendered, target, gateway=self.llm_gateway)
        except Exception as exc:
            import logging

            logging.getLogger("opencontext").warning("memory recall failed: %s", exc)
            return ""

    def _persist_local_context_pack_trace(
        self,
        query: str,
        manifest: ProjectManifest,
        candidates: list[ContextItem],
        ranked: list[ContextItem],
        pack_result: ContextPackResult,
        plan: EvidencePlan | None = None,
        *,
        aicx_checksum: str | None = None,
        aicx_metrics: dict[str, object] | None = None,
    ) -> RuntimeTrace:
        """Persist a sanitized local-only trace for CLI/API context packing."""

        trace_id = uuid4().hex
        root_span_id = uuid4().hex[:16]
        now = datetime.now(tz=UTC)
        budget = TokenBudgetManager(self.config.context).calculate()
        repo_map = self.render_repo_map(query)
        # Configurable rules engine: inject developer-authored rules/personas as a
        # high-priority, firewall-checked prompt section (gated; never blocks).
        _rules = None
        try:
            from opencontext_core.rules.loader import RulesLoader

            _rules = RulesLoader().resolve(project_root=Path(manifest.root))
        except Exception as exc:
            import logging

            logging.getLogger("opencontext").warning("rules loader failed: %s", exc)
        prompt = PromptAssembler().assemble(
            query,
            pack_result.included,
            provider_policy_summary=self._provider_policy_summary(),
            project_manifest=self._project_manifest_summary(manifest),
            repo_map=repo_map,
            workflow_contract=(
                "Local context-pack generation only. No provider call was made. "
                "Use included context as untrusted evidence and honor omissions."
            ),
            memory=self._recall_memory_for_prompt(query, Path(manifest.root)),
            rules=_rules,
        )
        trace = RuntimeTrace(
            run_id=uuid4().hex,
            trace_id=trace_id,
            span_id=root_span_id,
            parent_span_id=None,
            name="workflow.run",
            start_time=now,
            end_time=datetime.now(tz=UTC),
            attributes={
                "workflow.name": "context_pack.local",
                "provider.calls": 0,
                "context.selected_count": len(pack_result.included),
                "context.discarded_count": len(pack_result.omitted),
            },
            events=[
                TraceEvent(
                    name="context.pack.decisions",
                    timestamp=datetime.now(tz=UTC),
                    attributes={
                        "omissions": [
                            omission.model_dump(mode="json") for omission in pack_result.omissions
                        ],
                    },
                )
            ],
            spans=self._local_context_pack_spans(
                trace_id,
                root_span_id,
                now,
                candidates,
                ranked,
                pack_result,
                prompt.total_tokens,
            ),
            workflow_name="context_pack.local",
            input=query,
            provider="local-only",
            model="none",
            selected_context_items=pack_result.included,
            discarded_context_items=pack_result.omitted,
            token_budget=budget,
            token_estimates={
                "baseline_project": sum(file.tokens for file in manifest.files),
                "candidate_context": sum(item.tokens for item in candidates),
                "ranked_context": sum(item.tokens for item in ranked),
                "final_context_pack": pack_result.used_tokens,
                "prompt": prompt.total_tokens,
                "llm_input": 0,
                "llm_output": 0,
                "provider_calls": 0,
            },
            compression_strategy=self.config.context.compression.strategy.value,
            prompt_sections=prompt.sections,
            final_answer="[LOCAL_ONLY_CONTEXT_PACK]",
            timings_ms={},
            errors=[],
            created_at=datetime.now(tz=UTC),
            metadata={
                "local_only": True,
                "provider_calls": 0,
                "context_pack": pack_result.model_dump(mode="json"),
                "evidence_plan": plan.model_dump(mode="json") if plan is not None else None,
                "aicx_checksum": aicx_checksum,
                "aicx_metrics": aicx_metrics,
                "quality_inputs": {
                    "candidate_count": len(candidates),
                    "ranked_count": len(ranked),
                    "included_sources": [item.source for item in pack_result.included],
                    "omitted_sources": [item.source for item in pack_result.omitted],
                },
            },
        )
        sanitized_trace = TraceSanitizer().sanitize(trace, self.config.security.mode)
        ContextFirewall(self.config).check_trace_persistence(sanitized_trace).raise_if_blocked()
        self.trace_logger.persist(sanitized_trace)
        return sanitized_trace

    def _render_adapter_context(self, pack_result: ContextPackResult) -> str:
        if not pack_result.included:
            return "No project context selected."
        return "\n\n".join(
            "\n".join(
                [
                    f"### {index}. {item.source}",
                    f"type={item.source_type} priority={item.priority.name} score={item.score:.4f}",
                    item.content,
                ]
            )
            for index, item in enumerate(pack_result.included, start=1)
        )

    def _local_context_pack_spans(
        self,
        trace_id: str,
        root_span_id: str,
        start_time: datetime,
        candidates: list[ContextItem],
        ranked: list[ContextItem],
        pack_result: ContextPackResult,
        prompt_tokens: int,
    ) -> list[TraceSpan]:
        names_and_attributes: list[tuple[str, dict[str, object]]] = [
            ("workflow.run", {"workflow.name": "context_pack.local", "provider.calls": 0}),
            ("project.retrieve", {"context.candidate_count": len(candidates)}),
            ("context.rank", {"context.ranked_count": len(ranked)}),
            (
                "context.pack",
                {
                    "context.pack.used_tokens": pack_result.used_tokens,
                    "context.pack.available_tokens": pack_result.available_tokens,
                    "context.pack.included_count": len(pack_result.included),
                    "context.pack.omitted_count": len(pack_result.omitted),
                    "context.pack.omissions": [
                        omission.model_dump(mode="json") for omission in pack_result.omissions
                    ],
                },
            ),
            ("prompt.assemble", {"prompt.tokens": prompt_tokens}),
            ("trace.persist", {"trace.persisted": True}),
        ]
        spans: list[TraceSpan] = []
        for index, (name, attributes) in enumerate(names_and_attributes):
            spans.append(
                TraceSpan(
                    trace_id=trace_id,
                    span_id=root_span_id if index == 0 else uuid4().hex[:16],
                    parent_span_id=None if index == 0 else root_span_id,
                    name=name,
                    start_time=start_time,
                    end_time=datetime.now(tz=UTC),
                    attributes=attributes,
                )
            )
        return spans

    def _provider_policy_summary(self) -> str:
        provider = self.config.models.default.provider
        policy = next(
            (
                candidate
                for candidate in self.config.provider_policies
                if candidate.provider == provider
            ),
            None,
        )
        if policy is None:
            return f"Provider policy: {provider} has no configured policy and must fail closed."
        classifications = ", ".join(sorted(policy.allowed_classifications)) or "none"
        external = "enabled" if self.config.security.external_providers_enabled else "disabled"
        return (
            f"Provider policy: provider={provider}; external_providers={external}; "
            f"allowed={policy.allowed}; allowed_classifications={classifications}; "
            f"require_redaction={policy.require_redaction}."
        )

    def _project_manifest_summary(self, manifest: ProjectManifest) -> str:
        return (
            f"Project: {manifest.project_name}\n"
            f"Root: {manifest.root}\n"
            f"Profile: {manifest.profile}\n"
            f"Technology profiles: {', '.join(manifest.technology_profiles)}\n"
            f"Files: {len(manifest.files)}\n"
            f"Symbols: {len(manifest.symbols)}"
        )


def _classify_context_risk(query: str, *, evidence_count: int) -> RiskLevel:
    text = query.lower()
    sensitive_terms = ("secret", "token", "credential", "password", "private key")
    change_terms = ("change", "delete", "write", "modify", "deploy", "security")
    if evidence_count == 0 or any(term in text for term in sensitive_terms):
        return RiskLevel.HIGH
    if any(term in text for term in change_terms):
        return RiskLevel.HIGH
    return RiskLevel.NORMAL


def _verified_context_gates(
    evidence: Sequence[EvidenceItem],
    used_tokens: int,
    max_tokens: int | None,
    plan: EvidencePlan,
    risk_level: RiskLevel,
) -> list[GateSummary]:
    budget = max_tokens or plan.request.max_tokens
    stale = [
        item.source
        for item in plan.evidence
        if item.freshness
        in {FreshnessStatus.STALE, FreshnessStatus.UNKNOWN, FreshnessStatus.UNAVAILABLE}
    ]
    missing_provenance = [item.id for item in evidence if not item.source or not item.provenance]
    has_content = any((item.content or "").strip() for item in evidence)
    if not evidence:
        coverage_reason, coverage_risks = "no evidence available", ["missing_evidence"]
    elif not has_content:
        coverage_reason = "evidence present but all content is empty"
        coverage_risks = ["empty_content"]
    else:
        coverage_reason, coverage_risks = "evidence available", []
    return [
        GateSummary(
            name="coverage",
            passed=bool(evidence) and has_content,
            reason=coverage_reason,
            risks=coverage_risks,
        ),
        GateSummary(
            name="freshness",
            passed=not stale or risk_level is not RiskLevel.HIGH,
            reason="fresh evidence" if not stale else "high-risk context has stale evidence",
            risks=[] if not stale else ["stale_or_unknown_freshness"],
        ),
        GateSummary(
            name="provenance",
            passed=bool(evidence) and not missing_provenance,
            reason="source provenance available"
            if evidence and not missing_provenance
            else "missing source provenance",
            risks=[] if evidence and not missing_provenance else ["missing_provenance"],
        ),
        GateSummary(
            name="budget",
            passed=used_tokens <= budget,
            reason="within budget" if used_tokens <= budget else "context exceeds budget",
            risks=[] if used_tokens <= budget else ["context_over_budget"],
        ),
        GateSummary(
            name="policy",
            passed=plan.trust_decision.status == "sufficient",
            reason=plan.trust_decision.reason,
            risks=[] if plan.trust_decision.status == "sufficient" else ["insufficient_trust"],
        ),
    ]


__all__ = [
    "DECISION_CONTRACT_VERSION",
    "DECISION_EVENT_FAMILY",
    "ApplyResult",
    "ArchiveResult",
    "ArtifactSummary",
    "CollectingConsumer",
    "DecisionKind",
    "DecisionLog",
    "DecisionLogEntry",
    "DecisionRecorder",
    # Bus / store
    "EventBus",
    "EventCategory",
    "EventConsumer",
    "ExecutionContext",
    "ExecutionProfile",
    "ExecutionStrategy",
    "GateResult",
    "HarnessScheduler",
    "HistoryPort",
    "InspectionReport",
    "InspectionScope",
    "IntelligencePort",
    "JsonlEventBus",
    "KnowledgeGraphPort",
    "LiveState",
    "MutationRequest",
    "NextAction",
    "NextNodeDecision",
    "NodeResult",
    "NodeSpec",
    "NullRuntimeBrain",
    # Legacy facade (unchanged public contract)
    "OpenContextRuntime",
    "PreparedContext",
    "ProjectSetupResult",
    "ReceiptSummary",
    "RunRequest",
    "RunResult",
    # PR-001 facade + DTOs
    "RuntimeApi",
    "RuntimeBrain",
    "RuntimeBrainPort",
    # Convergence seams
    "RuntimeDecision",
    "RuntimeErrorCode",
    "RuntimeEvent",
    "RuntimeEventInput",
    "RuntimeFailure",
    "RuntimeMode",
    "RuntimeResult",
    "RuntimeRun",
    "RuntimeScheduler",
    # Models / enums
    "RuntimeSession",
    "Scheduler",
    "SchedulingDecision",
    "SelectionKind",
    "SessionRef",
    "SessionState",
    "SessionStatus",
    "SessionStore",
    "SimulationReport",
    "StartSessionRequest",
    # State machine / runner
    "StateMachine",
    "TransitionDecision",
    "WorkflowRunner",
    "WorkflowSpec",
    "make_event",
    "redact_chain_of_thought",
    "resolve_strategy",
    "summarize_decision_log",
]
