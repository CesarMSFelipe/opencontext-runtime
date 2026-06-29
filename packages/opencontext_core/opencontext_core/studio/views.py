"""Read-only Studio view models (PR-014, OC-STUDIO-001).

Framework-free, serializable projections of existing run evidence. Every field
is defaulted/optional so a partial or missing artifact still yields a valid
view, and **no model here carries a write/mutate method** — the read-only
invariant (SPEC-STU-014-11) is structural.

The book's canonical contract names (``RuntimeSession``/``Receipt``/
``ContextEnvelope``/``KgSubgraph``/``HarnessResult``/``ConfidenceReport``/
``BenchmarkResult``) are the eventual source; these views bind to today's
analogues (``RuntimeSession``/``LiveState``/``OcNewRunState``/``RunReceipt``/
``PhaseResultEnvelope``/``HarnessReport``/``ProviderReceipt``/``CapabilityGraph``
/``LearningCandidate``). The reader is the single swap point when the named
contracts land — these views stay unchanged.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StudioSession(BaseModel):
    """Session dashboard row (SPEC-STU-014-03)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str = "session"  # "session" (PR-002 SessionStore) | "run" (legacy oc_new)
    task: str = ""
    workflow: str | None = None
    profile: str | None = None
    status: str = "unknown"
    current_node: str | None = None
    elapsed_s: float | None = None
    cost: float | None = None
    confidence: float | None = None  # None until PR-011 surfaces it per session
    next_action: str | None = None
    updated_at: str = ""


class StudioTimelineNode(BaseModel):
    """One node/phase on the workflow timeline (SPEC-STU-014-04)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: str = "pending"
    persona: str | None = None
    skill: str | None = None
    gate_blocked: bool = False
    gate_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None


class StudioTimeline(BaseModel):
    """Workflow timeline / live workflow view (SPEC-STU-014-04)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    current_node: str | None = None
    nodes: list[StudioTimelineNode] = Field(default_factory=list)


class StudioEvent(BaseModel):
    """One projected runtime event."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = ""
    ts: str = ""
    category: str = ""
    type: str = ""
    status: str = ""
    message: str = ""
    node: str | None = None


class StudioEventLane(BaseModel):
    """One event-family lane (doc 60 item 12)."""

    model_config = ConfigDict(extra="forbid")

    lane: str
    categories: list[str] = Field(default_factory=list)
    events: list[StudioEvent] = Field(default_factory=list)


class StudioTimelines(BaseModel):
    """Event-family timelines: execution / decision / context / memory / kg."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    available: bool = False
    lanes: list[StudioEventLane] = Field(default_factory=list)


class StudioContextLayer(BaseModel):
    """One context-envelope layer (L1/L2/L3) with its token budget."""

    model_config = ConfigDict(extra="forbid")

    name: str
    token_budget: int = 0
    tokens_used: int = 0
    sources: list[str] = Field(default_factory=list)


class StudioContextView(BaseModel):
    """Context-envelope viewer (SPEC-STU-014-05) + budget breakdown (STU-CONV)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    available: bool = False
    layers: list[StudioContextLayer] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    omissions: list[str] = Field(default_factory=list)
    token_budget: int = 0
    compression_receipts: list[str] = Field(default_factory=list)


class StudioKgNode(BaseModel):
    """One KG node in the session subgraph."""

    model_config = ConfigDict(extra="forbid")

    id: str = ""
    kind: str = ""
    name: str = ""
    path: str = ""


class StudioKgView(BaseModel):
    """Knowledge Graph explorer subgraph (SPEC-STU-014-06)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    available: bool = False
    query: str = ""
    nodes: list[StudioKgNode] = Field(default_factory=list)


class StudioMemoryRecord(BaseModel):
    """One memory record with its lifecycle marker (SPEC-STU-014-07)."""

    model_config = ConfigDict(extra="forbid")

    id: str = ""
    content: str = ""
    status: str = ""  # retrieved | candidate | promoted | rejected | superseded
    superseded: bool = False
    superseded_by: str | None = None
    conflict: str | None = None


class StudioMemoryView(BaseModel):
    """Memory viewer (SPEC-STU-014-07)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    available: bool = False
    records: list[StudioMemoryRecord] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class StudioReceipt(BaseModel):
    """One receipt (phase or run) with its checksums (SPEC-STU-014-08)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = ""
    change_id: str = ""
    phase: str = ""
    status: str = ""
    duration_s: float = 0.0
    summary: str = ""
    checksums: dict[str, str] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    missing_artifacts: list[str] = Field(default_factory=list)


class StudioReceiptView(BaseModel):
    """Patch / receipts viewer (SPEC-STU-014-08)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    available: bool = False
    changed_files: list[str] = Field(default_factory=list)
    receipts: list[StudioReceipt] = Field(default_factory=list)
    rollback_checkpoint: str | None = None


class StudioHarnessView(BaseModel):
    """Harness / gates view (SPEC-STU-014-08)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    available: bool = False
    passed: bool = False
    failures: list[str] = Field(default_factory=list)
    duration_s: float = 0.0
    run_id: str = ""
    change_id: str = ""


class StudioCostView(BaseModel):
    """Cost / runtime-intelligence dashboard (SPEC-STU-014-09)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    available: bool = False
    estimated_cost: float = 0.0
    actual_cost: float | None = None  # None until separate actual telemetry exists
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    token_savings: int = 0
    confidence: float | None = None  # nullable; sourced by PR-011
    calls: int = 0


class StudioCapabilityNode(BaseModel):
    """One capability with actionable remediation (STU-CONV Capability Graph)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    available: bool = False
    evidence: str = ""
    version: str | None = None
    unmet_dependencies: list[str] = Field(default_factory=list)
    remediation: str = ""


class StudioCapabilityView(BaseModel):
    """Capability Graph view (STU-CONV)."""

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    nodes: list[StudioCapabilityNode] = Field(default_factory=list)


class StudioDecision(BaseModel):
    """One Decision Log entry (rationale only, never chain-of-thought)."""

    model_config = ConfigDict(extra="forbid")

    id: str = ""
    kind: str = ""
    chosen: str = ""
    rationale: str = ""
    confidence: float | None = None
    created_at: str = ""


class StudioDecisionLogView(BaseModel):
    """Decision Log view (STU-CONV)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    available: bool = False
    decisions: list[StudioDecision] = Field(default_factory=list)


class StudioBrainView(BaseModel):
    """Runtime Brain / Scheduler view (STU-CONV)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    available: bool = False
    recommended_next_node: str | None = None
    persona: str | None = None
    skill: str | None = None
    rationale: str = ""
    governed_by: str = ""  # the state-machine transition that governed the recommendation


class StudioCacheView(BaseModel):
    """Cache metrics view (STU-CONV)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    available: bool = False
    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    token_savings: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)


class StudioLearningCandidate(BaseModel):
    """One learning candidate with benchmark evidence (STU-CONV)."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = ""
    kind: str = ""
    summary: str = ""
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)
    promote_requested: bool = True  # Studio requests — never enforces — promotion


class StudioLearningView(BaseModel):
    """Learning candidates view (STU-CONV)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    available: bool = False
    candidates: list[StudioLearningCandidate] = Field(default_factory=list)


class StudioConfigView(BaseModel):
    """Config / profile + plugin read surface (SPEC-STU-014-10)."""

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    profile: str = ""
    studio_enabled: bool = False
    plugins: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)  # config doctor findings (read-only)


# --- N2 read-only surfacing (AVH-019) -----------------------------------------
# Decision-log surfacing already exists above (StudioDecisionLogView). The three
# views below add the remaining N2 panels: no-op/blocked task history, the last
# release-gate verdict, and benchmark coverage. All are projections of existing
# on-disk evidence and carry no write/mutate method (read-only invariant).


class StudioTaskStatus(BaseModel):
    """One run that ended in a non-``completed`` terminal status (AVH-019)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = ""
    session_id: str = ""
    task: str = ""
    workflow: str = ""
    status: str = ""  # blocked | escalated | needs_executor | needs_provider | needs_user_edit
    reason: str = ""  # completion / blocking reason
    mutation_required: bool = False
    updated_at: str = ""


class StudioTaskHistoryView(BaseModel):
    """No-op / blocked task history (AVH-019 (b)).

    Lists runs whose terminal status is one of the OC Flow honesty statuses, with
    the recorded blocking reason — so a no-op mutation run is never silent.
    """

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    statuses: list[str] = Field(default_factory=list)  # the filter set applied
    tasks: list[StudioTaskStatus] = Field(default_factory=list)


class StudioGateResult(BaseModel):
    """One release-gate verdict row (AVH-019 (c))."""

    model_config = ConfigDict(extra="forbid")

    gate: str = ""
    category: str = ""
    status: str = ""  # MET | FAILED | NOT_MEASURED
    detail: str = ""


class StudioReleaseGateView(BaseModel):
    """Release-gate status panel from the last ``release acceptance`` run (AVH-019 (c))."""

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    ready: bool = False
    met: int = 0
    not_measured: int = 0
    failed: int = 0
    gates: list[StudioGateResult] = Field(default_factory=list)


class StudioBenchmarkSuiteCoverage(BaseModel):
    """Per-suite benchmark coverage row (AVH-019 (d))."""

    model_config = ConfigDict(extra="forbid")

    suite: str = ""
    measured: bool = False
    success: int = 0
    total: int = 0


class StudioBenchmarkCoverageView(BaseModel):
    """Benchmark coverage summary from the last recorded run (AVH-019 (d))."""

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    total_suites: int = 0
    measured_suites: int = 0
    suites: list[StudioBenchmarkSuiteCoverage] = Field(default_factory=list)
