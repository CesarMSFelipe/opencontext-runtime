# 54 — Requirement-to-PR Traceability Matrix

Authority: `OC-FINAL-CONVERGENCE-001.md` §7.2 (and §7 Output 1 / §11). This matrix traces **every** requirement in the SDD program — one row per `### Requirement:` block across the 22 change specs under `.sdd/changes/pr-*/` — to its source architecture document, owning PR, primary target module, covering test, acceptance-gate benchmark, and reconciliation status. Requirement IDs, titles, and statuses are pulled verbatim from each `spec.md`; Module / Test / Benchmark are best-effort (`(new)` = greenfield, `tbd` = test not yet bound, `—` = no matching gate).

**Columns:** `Requirement | Source Doc | PR | Module | Test | Benchmark | Status`.

**Status legend:** `MET` = present and cited in code; `PROPOSED` = absent or partial (greenfield for this PR); `DEFERRED` = assigned to a downstream / 1.x PR with reason.

**Totals:** 453 requirements across 22 PRs — **118 MET**, **302 PROPOSED**, **33 DEFERRED**.

**Benchmark gates** referenced below are the mandatory 1.0 acceptance gates defined in `57-final-1-0-acceptance-gates.md` §A: `first-run`, `oc-flow-localized-bugfix`, `sdd-formal-feature`, `context-token-efficiency`, `kg-retrieval-precision`, `memory-usefulness`, `policy-security`, `plugin-compatibility`, `provider-fallback`, `resume-rollback`.

---

## PR-000 Meta Planning & Intent Engine

Change folder: `pr-000-meta-planning` · Source: `OC-FINAL-CONVERGENCE-001.md §5` · 14 requirements (3 MET / 10 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **MP-001** Workflow-neutral planning package | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `planning/ (new)` | tbd | — | PROPOSED |
| **MP-002** Structured intent record | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `planning/ (new)` | tbd | — | PROPOSED |
| **MP-003** Intent maps to architecture docs | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `planning/ (new)` | tbd | — | PROPOSED |
| **MP-004** Intent decomposes into typed slices | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `planning/ (new)` | tbd | — | PROPOSED |
| **MP-005** Slices assigned to PRs with a dependency graph | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `planning/ (new)` | tbd | — | PROPOSED |
| **MP-006** Each slice carries a program-scoped risk assessment | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `planning/ (new)` | tbd | — | PROPOSED |
| **MP-007** Each slice carries a cost estimate and a recommended workflow | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `planning/ (new)` | tbd | — | PROPOSED |
| **MP-008** Program-scoped requirement coverage map | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `planning/ (new)` | tbd | — | PROPOSED |
| **MP-009** Build fails on any orphaned requirement | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `planning/ (new)` | tbd | — | PROPOSED |
| **MP-010** ProgramPlan persisted as an artifact with a receipt | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `planning/ (new)` | tbd | — | PROPOSED |
| **MP-011** ComplianceMatrix coverage primitive | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `verify/compliance.py` | tbd | — | MET |
| **MP-012** Plan persists via the existing artifact store | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `agents/artifact_store.py` | tbd | — | MET |
| **MP-013** Plan receipts use AgenticReceipt | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `agentic/receipt.py` | tbd | — | MET |
| **MP-014** Slice execution and plan-outcome learning loop | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-meta-planning` | `planning/ (new)` | tbd | — | DEFERRED |

## PR-000.1 Runtime Brain & Scheduler

Change folder: `pr-000-1-runtime-brain` · Source: `OC-FINAL-CONVERGENCE-001.md §5` · 12 requirements (2 MET / 9 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **RB-001** Decision-layer modules exist | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-1-runtime-brain` | `brain.py (new)` | tbd | — | PROPOSED |
| **RB-002** Every selection is a typed RuntimeDecision | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-1-runtime-brain` | `runtime/brain/ (new)` | tbd | — | PROPOSED |
| **RB-003** Per-run append-only Decision Log | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-1-runtime-brain` | `runtime/brain/ (new)` | tbd | — | PROPOSED |
| **RB-004** The Scheduler proposes the next node | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-1-runtime-brain` | `runtime/brain/ (new)` | tbd | — | PROPOSED |
| **RB-005** Brain covers all eight selection kinds | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-1-runtime-brain` | `runtime/brain/ (new)` | tbd | — | PROPOSED |
| **RB-006** Unified execution strategy | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-1-runtime-brain` | `runtime/brain/ (new)` | tbd | — | PROPOSED |
| **RB-007** Recommendations are advisory; the State Machine decides transitions | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-1-runtime-brain` | `runtime/brain/ (new)` | tbd | — | PROPOSED |
| **RB-008** No hidden agent-only orchestration | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-1-runtime-brain` | `runtime/brain/ (new)` | tbd | — | PROPOSED |
| **RB-009** Adaptive but not opaque | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-1-runtime-brain` | `runtime/brain/ (new)` | tbd | — | PROPOSED |
| **RB-010** Reuse AgenticReceipt for decision receipts | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-1-runtime-brain` | `agentic/receipt.py` | tbd | — | MET |
| **RB-011** Decision Log extends existing PolicyDecision evidence | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-1-runtime-brain` | `models/run_envelope.py` | `tests/core/test_run_envelope.py` | `policy-security` | MET |
| **RB-012** Studio decision-timeline view | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-1-runtime-brain` | `runtime/brain/ (new)` | tbd | — | DEFERRED |

## PR-000.2 Capability Graph & Execution Profiles

Change folder: `pr-000-2-capability-profiles` · Source: `OC-FINAL-CONVERGENCE-001.md §5` · 14 requirements (3 MET / 9 PROPOSED / 2 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **CP-001** Detect local test/lint/type tooling without executing it | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `sdd_runtime.py` | `tests/core/test_sdd_runtime.py` | — | MET |
| **CP-002** Doctor command reports environment health | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `packages/opencontext_cli/opencontext_cli/main.py` | tbd | `first-run` | MET |
| **CP-003** Per-client feature capability matrix | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `configurator/capability.py` | `tests/core/test_capability.py` | — | MET |
| **CP-004** capabilities/ package with CapabilityNode/CapabilityGraph/CapabilityConstraint | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `runtime/capabilities/ (new)` | tbd | — | PROPOSED |
| **CP-005** Capabilities declare dependencies in the graph | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `runtime/capabilities/ (new)` | tbd | — | PROPOSED |
| **CP-006** doctor materialises the CapabilityGraph | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `runtime/capabilities/ (new)` | tbd | `first-run` | PROPOSED |
| **CP-007** profiles/ package with ExecutionProfile and ExecutionProfileStrategy | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `runtime/capabilities/ (new)` | tbd | — | PROPOSED |
| **CP-008** balanced / low-cost / enterprise / research / performance profiles | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `runtime/capabilities/ (new)` | tbd | — | PROPOSED |
| **CP-009** fast / cheap / careful / enterprise / research / local_first strategies | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `runtime/capabilities/ (new)` | tbd | — | PROPOSED |
| **CP-010** A profile binds the four runtime levers as one unit | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `runtime/capabilities/ (new)` | tbd | — | PROPOSED |
| **CP-011** Workflow selection uses capability availability and degrades gracefully | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `runtime/capabilities/ (new)` | tbd | — | PROPOSED |
| **CP-012** Resolver produces a decision-input snapshot | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `runtime/capabilities/ (new)` | tbd | — | PROPOSED |
| **CP-013** WorkflowDefinition.required_capabilities | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `runtime/capabilities/ (new)` | tbd | `first-run` | DEFERRED |
| **CP-014** Runtime Brain reads graph + profile for next-node decisions | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-2-capability-profiles` | `runtime/capabilities/ (new)` | tbd | — | DEFERRED |

## PR-000.3 Semantic Cache & Runtime Optimizer

Change folder: `pr-000-3-semantic-cache` · Source: `OC-FINAL-CONVERGENCE-001.md §5` · 14 requirements (5 MET / 8 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **SC-001** Shared CacheEntry base + four typed entries | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `cache/ (new)` | tbd | — | PROPOSED |
| **SC-002** Exact prompt/response cache | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `cache/exact.py` | tbd | — | MET |
| **SC-003** SemanticCacheEntry + semantic_cache.py | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `cache/semantic_cache.py (new)` | tbd | — | PROPOSED |
| **SC-004** ToolCacheEntry + tool_cache.py | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `cache/tool_cache.py (new)` | tbd | — | PROPOSED |
| **SC-005** AstCacheEntry + ast_cache.py (file-invalidated) | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `cache/ast_cache.py (new)` | tbd | — | PROPOSED |
| **SC-006** ProviderCacheEntry + provider_cache.py | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `cache/provider_cache.py (new)` | tbd | — | PROPOSED |
| **SC-007** Stable cache-friendly prompt prefixes | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `compression/cache_aligner.py` | `tests/core/test_cache_aligner.py` | — | MET |
| **SC-008** KgQuery + MemoryRetrieval caches | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `cache/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **SC-009** CacheInvalidationRule + file-change invalidation | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `cache/invalidation.py (new)` | tbd | — | PROPOSED |
| **SC-010** Content-addressed keys + redaction | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `cache/base.py` | tbd | `policy-security` | MET |
| **SC-011** Classification fail-closed eligibility | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `cache/base.py` | tbd | — | MET |
| **SC-012** CCR cache reuse with hit/miss stats | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `compression/ccr_cache.py` | `tests/core/test_ccr_cache.py` | — | MET |
| **SC-013** RuntimeOptimizationRecommendation + optimizer | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `optimization/optimizer.py (new)` | tbd | — | PROPOSED |
| **SC-014** Intelligence consumption + token/tool benchmark gate | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-3-semantic-cache` | `cache/ (new)` | tbd | `context-token-efficiency` | DEFERRED |

## PR-000.4 Decision Log & Learning Loop

Change folder: `pr-000-4-decision-log-learning` · Source: `OC-FINAL-CONVERGENCE-001.md §5` · 14 requirements (4 MET / 9 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **DL-001** DecisionLogEntry + append-only DecisionLog | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/ (new)` | tbd | — | PROPOSED |
| **DL-002** Record why each runtime selection was made | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/ (new)` | tbd | — | PROPOSED |
| **DL-003** Typed learning candidate + outcome with classification | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/ (new)` | tbd | — | PROPOSED |
| **DL-004** Typed runtime feedback over the capture substrate | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/ (new)` | tbd | — | PROPOSED |
| **DL-005** ImprovementProposal aligns with existing EvolutionProposal | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/evolution_store.py (new)` | tbd | — | PROPOSED |
| **DL-006** LearningLoop feeds Memory Harness + Runtime Intelligence | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/ (new)` | tbd | — | PROPOSED |
| **DL-007** No-CoT redaction on every persisted field | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/ (new)` | tbd | `policy-security` | PROPOSED |
| **DL-008** Loop proposes promotions; it does not write durable memory | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/ (new)` | tbd | — | PROPOSED |
| **DL-009** No improvement promotion without benchmark evidence | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/ (new)` | tbd | — | PROPOSED |
| **DL-010** EvolutionEngine post-run extractor | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/evolution_engine.py` | tbd | — | MET |
| **DL-011** EvolutionStore + EvolutionApplier + ProposalEngine | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/evolution_store.py` | tbd | — | MET |
| **DL-012** FeedbackCollector + OperationMetrics + record_outcome | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/feedback_collector.py` | tbd | — | MET |
| **DL-013** Append-only RunEvent ledger for decision replay | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `models/trace.py` | tbd | — | MET |
| **DL-014** Decision-timeline visualisation | `OC-FINAL-CONVERGENCE-001.md §5` | `pr-000-4-decision-log-learning` | `learning/ (new)` | tbd | — | DEFERRED |

## PR-001 Runtime Core

Change folder: `pr-001-runtime-core` · Source: `02-runtime-architecture.md` · 23 requirements (3 MET / 19 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **RC-001** Workflow-neutral RuntimeApi facade | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-002** RuntimeSession with 9-status enum | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-003** RuntimeRun belongs to a session | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-004** RuntimeEvent with required categories | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-005** Append-only JSONL event stream | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-006** On-disk session layout with live state | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-007** Every transition is validated | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-008** Runner drives one run | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-009** NodeResult evidence shape | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-010** Standard node pipeline | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-011** Six runtime modes | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-012** RuntimeErrorCode enum | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-013** Legacy runs execute inside a session | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-014** RunEnvelope evidence record | `02-runtime-architecture.md` | `pr-001-runtime-core` | `models/run_envelope.py` | `tests/core/test_run_envelope.py` | — | MET |
| **RC-015** AgenticReceipt v2 | `02-runtime-architecture.md` | `pr-001-runtime-core` | `agentic/receipt.py` | tbd | — | MET |
| **RC-016** RunStore index | `02-runtime-architecture.md` | `pr-001-runtime-core` | `harness/run_store.py` | `tests/core/test_run_store.py` | — | MET |
| **RC-017** Durable stores, checkpoints, artifact-aware resume | `02-runtime-architecture.md` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | `resume-rollback` | DEFERRED |
| **RC-CONV** RuntimeDecision skeleton | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-CONV** DecisionLog skeleton attachable to a run | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-CONV** ExecutionProfile snapshot on session | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-CONV** Capability snapshot on session | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-CONV** Runtime Brain placeholder interface | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |
| **RC-CONV** Scheduler placeholder interface | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-001-runtime-core` | `runtime/ (new)` | tbd | — | PROPOSED |

## PR-002 Artifacts, Receipts & Resume

Change folder: `pr-002-artifacts-receipts` · Source: `24-artifact-receipt-lifecycle.md` · 20 requirements (5 MET / 14 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **ART-01** Artifact references carry kind, path, and content checksum | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `models/run_envelope.py` | `tests/core/test_run_envelope.py` | `resume-rollback` | MET |
| **ART-02** ArtifactStore exposes write/get/list_for_run/verify_checksum | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **REC-01** ReceiptStore writes immutable, queryable receipts per run | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `operating_model/receipts.py` | tbd | `resume-rollback` | MET |
| **REC-02** Receipt model carries action/reason/evidence and a valid kind | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **MAN-01** Each run owns a RunManifest indexing its evidence | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **APR-01** Every mutation produces an ApplyReceipt | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **CHK-01** A checkpoint snapshots target files before any write | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `harness/checkpoint.py` | `tests/harness/test_checkpoint.py` | `resume-rollback` | MET |
| **CHK-02** CheckpointManager records per-file checksums in a Checkpoint model | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **RES-01** A run can resume by skipping already-completed phases | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `harness/runner.py` | tbd | `resume-rollback` | MET |
| **RES-02** Resume validates artifact integrity and fails safely if missing | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **RBK-01** A failed or rejected mutation rolls back to the checkpoint | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `harness/phases.py` | tbd | `resume-rollback` | MET |
| **RBK-02** Rollback emits a receipt, an event, and a report artifact | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **SES-01** Durable session/run layout with patches, retention, and a kill-switch | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **STU-01** Studio renders the artifact/receipt/checkpoint timeline | `24-artifact-receipt-lifecycle.md` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | DEFERRED |
| **AR-CONV** Decision Log artifact kind | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **AR-CONV** ProgramPlan artifact kind | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **AR-CONV** Cache-metadata support on artifacts | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **AR-CONV** Artifact source classification | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **AR-CONV** Resume validation for Decision Log | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **AR-CONV** Resume validation for profile/capability snapshot | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-002-artifacts-receipts` | `artifacts/ (new)` | tbd | `resume-rollback` | PROPOSED |

## PR-003 Workflow Registry

Change folder: `pr-003-workflow-registry` · Source: `03-sdd-workflow-architecture.md` · 20 requirements (1 MET / 18 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **WD1** Declarative versioned workflow definition | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | `first-run` | PROPOSED |
| **WN1** Each node declares persona, required harnesses, and output contracts | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | — | PROPOSED |
| **WE1** Edges are declarative with optional conditions | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | — | PROPOSED |
| **WR1** Register, get, list, and describe workflows | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | — | PROPOSED |
| **WR2** Alias table maps legacy names to a workflow id + profile | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | — | PROPOSED |
| **RES1** Runtime resolves a definition before scheduling phases | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | `first-run` | PROPOSED |
| **BAK1** Existing workflow names continue to resolve to their historical phase sets | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `harness/runner.py` | tbd | — | MET |
| **SDD1** SDD is registered as a declarative built-in workflow | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | `sdd-formal-feature` | PROPOSED |
| **YAML1** Built-in SDD workflow loads from a YAML template | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | `sdd-formal-feature` | PROPOSED |
| **VAL1** Definitions are validated for structural integrity | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | `first-run` | PROPOSED |
| **EVT1** Resolution and validation emit typed events | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | — | PROPOSED |
| **RCPT1** Workflow selection is recorded in a receipt | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | — | PROPOSED |
| **FLAG1** registry_enabled toggles legacy resolution | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | — | PROPOSED |
| **INT1** Execution keeps delegating to the existing HarnessRunner | `03-sdd-workflow-architecture.md` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | — | DEFERRED |
| **WR-CONV** Workflow selection policy | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | `policy-security` | PROPOSED |
| **WR-CONV** Workflow strategy metadata | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | — | PROPOSED |
| **WR-CONV** Workflow cost/risk metadata | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | — | PROPOSED |
| **WR-CONV** Workflow↔profile compatibility | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **WR-CONV** Workflow↔capability compatibility | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **WR-CONV** Explicit SDD/OC-Flow coexistence validation | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-003-workflow-registry` | `workflow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |

## PR-004 SDD Hardening

Change folder: `pr-004-sdd-hardening` · Source: `03-sdd-workflow-architecture.md` · 19 requirements (8 MET / 10 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **REQ-01** The SDD flow declares the canonical nine phases in order | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `agents/sdd_orchestrator.py` | `tests/core/test_sdd_orchestrator.py` | `sdd-formal-feature` | MET |
| **REQ-02** SDD is registered as one WorkflowDefinition in the registry | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `config.py (new)` | tbd | `first-run` | PROPOSED |
| **REQ-03** Each phase declares the persona that drives it | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `personas.py` | `tests/configurator/test_personas.py` | `sdd-formal-feature` | MET |
| **REQ-04** Each phase declares and enforces its required/expected artifacts | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `oc_new/flow.py` | tbd | `sdd-formal-feature` | MET |
| **REQ-05** Each phase declares its required harnesses as a first-class field | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `harness/config.py (new)` | tbd | `sdd-formal-feature` | PROPOSED |
| **REQ-06** A uniform receipt is emitted for every phase | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `harness/runner.py (new)` | tbd | `sdd-formal-feature` | PROPOSED |
| **REQ-07** The propose phase runs the wired executor | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `harness/phases.py` | tbd | `sdd-formal-feature` | MET |
| **REQ-08** Propose reports honestly when no real executor produced the proposal | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `sdd/ (new)` | tbd | `sdd-formal-feature` | PROPOSED |
| **REQ-09** Resume skips phases that already completed | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `harness/runner.py` | tbd | `resume-rollback` | MET |
| **REQ-10** Resume rehydrates prior-phase artifacts into the resumed run | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `harness/runner.py (new)` | tbd | `resume-rollback` | PROPOSED |
| **REQ-11** Verify runs locally and never fabricates success | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `harness/phases.py` | tbd | `sdd-formal-feature` | MET |
| **REQ-12** Verify must not report "all checks passed" when no test ran | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `harness/phases.py (new)` | tbd | `sdd-formal-feature` | PROPOSED |
| **REQ-13** SDD is driven by a single workflow spine | `03-sdd-workflow-architecture.md` | `pr-004-sdd-hardening` | `harness/runner.py (new)` | tbd | `sdd-formal-feature` | DEFERRED |
| **SDD-CONV** Phase-level contracts | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-004-sdd-hardening` | `oc_new/flow.py` | tbd | `sdd-formal-feature` | MET |
| **SDD-CONV** Phase-level artifacts | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-004-sdd-hardening` | `oc_new/flow.py` | tbd | `sdd-formal-feature` | MET |
| **SDD-CONV** Phase-level decision receipts | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-004-sdd-hardening` | `sdd/ (new)` | tbd | `sdd-formal-feature` | PROPOSED |
| **SDD-CONV** Handoff artifacts between phases | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-004-sdd-hardening` | `sdd/ (new)` | tbd | `sdd-formal-feature` | PROPOSED |
| **SDD-CONV** Scaffold blocking in strict mode | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-004-sdd-hardening` | `sdd/ (new)` | tbd | `sdd-formal-feature` | PROPOSED |
| **SDD-CONV** Meta-plan awareness (consume ProgramPlan from PR-000) | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-004-sdd-hardening` | `sdd/ (new)` | tbd | `sdd-formal-feature` | PROPOSED |

## PR-005 Policy Engine

Change folder: `pr-005-policy-engine` · Source: `15-policy-security-architecture.md` · 27 requirements (11 MET / 14 PROPOSED / 2 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **PE-1** Single runtime evaluation entry point | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **PE-2** Canonical decision with allow/warn/ask/deny and evidence | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **PE-3** Four built-in presets with balanced default | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **PE-4** Deny-by-default, fail-closed posture | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `config.py` | `tests/core/test_config.py` | `policy-security` | MET |
| **FILE-1** Writes to forbidden paths are blocked before any mutation | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `harness/phases.py` | tbd | `policy-security` | MET |
| **CMD-1** Denied commands do not execute | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **CMD-2** Commands are classified into risk categories | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **NET-1** Network access is denied unless explicitly allowed | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `actions/policy.py` | tbd | `policy-security` | MET |
| **PROV-1** Provider calls are secret-checked and policy-gated | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `safety/firewall.py` | tbd | `policy-security` | MET |
| **SECRET-1** Secrets are detected before provider/memory/export sinks | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `safety/secrets.py` | tbd | `policy-security` | MET |
| **MEM-1** Memory writes exclude chain-of-thought and credentials | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **PLUGIN-1** Plugins are deny-by-default and explicitly permissioned | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `plugins/manifest.py` | tbd | `policy-security` | MET |
| **AUTO-1** Auto-apply is gated by change risk | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **APPROVAL-1** Unapproved writes are blocked | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `harness/gates.py` | tbd | `policy-security` | MET |
| **APPROVAL-2** ask decisions pause, prompt, and record a policy receipt | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **HARNESS-1** A harness gate consumes policy output | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `harness/gates.py` | tbd | `policy-security` | MET |
| **EVENT-1** Policy decisions emit named events | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **STUDIO-1** Studio surfaces policy decisions and findings | `15-policy-security-architecture.md` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | DEFERRED |
| **POL-CONV** Cache governance | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **POL-CONV** Provider-call governance | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-005-policy-engine` | `safety/firewall.py` | tbd | `policy-security` | MET |
| **POL-CONV** Memory-write governance | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-005-policy-engine` | `memory_usability/novelty_gate.py` | `tests/core/test_novelty_gate.py` | `policy-security` | MET |
| **POL-CONV** KG-write governance | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **POL-CONV** Plugin-permission governance | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-005-policy-engine` | `plugins/manifest.py` | tbd | `policy-security` | MET |
| **POL-CONV** Studio-approval governance | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | DEFERRED |
| **POL-CONV** Execution-profile governance | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **POL-CONV** Remote/CI-mode governance | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |
| **POL-CONV** Policy decisions recorded in the Decision Log (AC fold) | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-005-policy-engine` | `policy/ (new)` | tbd | `policy-security` | PROPOSED |

## PR-006 Persona, Skill & Harness Registries

Change folder: `pr-006-registries` · Source: `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` · 28 requirements (7 MET / 18 PROPOSED / 3 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **PR-006-PERSONA** PersonaDefinition first-class schema | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | `first-run` | PROPOSED |
| **PR-006-PERSONA** PersonaRegistry | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **PR-006-PERSONA** Twelve canonical built-in personas registered | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `personas.py` | `tests/configurator/test_personas.py` | — | MET |
| **PR-006-PERSONA** oc-diagnostician and oc-security-reviewer | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | `policy-security` | PROPOSED |
| **PR-006-PERSONA** PersonaResolver with role overrides | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **PR-006-PERSONA** PersonaHandoff is explicit and persisted | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `oc_new/models.py` | tbd | — | MET |
| **PR-006-PERSONA** Persona tool permissions enforced via Policy Engine | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `tools/policy.py` | tbd | `policy-security` | MET |
| **PR-006-PERSONA** Persona failure semantics vocabulary | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **PR-006-SKILL** SkillDefinition contract schema | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | `first-run` | PROPOSED |
| **PR-006-SKILL** SkillRegistry discovers and indexes skills | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `skills/registry.py` | tbd | — | MET |
| **PR-006-SKILL** ~24 categorized built-in skills, bundles, and tiers | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **PR-006-SKILL** Skill lifecycle resolve→validate→execute→validate→receipt | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **PR-006-SKILL** Skill benchmarking and policy auto-disable | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | `policy-security` | DEFERRED |
| **PR-006-HARNESS** HarnessRegistry and HarnessDefinition | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | `first-run` | PROPOSED |
| **PR-006-HARNESS** HarnessResult type | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `harness/models.py` | tbd | — | MET |
| **PR-006-HARNESS** GateResult with severity, evidence, and blocking | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **PR-006-HARNESS** Thirteen named built-in harnesses | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **PR-006-HARNESS** Phase→gate matrix | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `harness/config.py` | `tests/core/test_config.py` | — | MET |
| **PR-006-HARNESS** Workflow → harness mode matrix and plugin harnesses | `05-persona-architecture.md / 06-skill-architecture.md / 07-harness-architecture.md` | `pr-006-registries` | `registries/ (new)` | tbd | — | DEFERRED |
| **REG-CONV** PersonaStrategy | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **REG-CONV** PersonaCapabilities | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **REG-CONV** PersonaConstraints | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **REG-CONV** Skill tiers | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **REG-CONV** Skill benchmark metadata | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-006-registries` | `registries/ (new)` | tbd | — | DEFERRED |
| **REG-CONV** Harness false-positive metrics | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **REG-CONV** Harness strictness-by-profile | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **REG-CONV** Plugin-ready registry metadata | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-006-registries` | `registries/ (new)` | tbd | — | PROPOSED |
| **REG-CONV** Harnesses are deterministic governance components (AC fold) | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-006-registries` | `harness/runner.py` | tbd | — | MET |

## PR-007 OC Flow MVP

Change folder: `pr-007-oc-flow` · Source: `04-oc-flow-architecture.md` · 24 requirements (0 MET / 23 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **FLOW-1** OC Flow registered as a declarative WorkflowDefinition | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `first-run` | PROPOSED |
| **FLOW-2** Conditional edge set drives node transitions | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-3** Each node declares inputs, outputs and exit conditions | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-4** plan produces a frozen TaskContract | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-5** diagnose records a structured, evidence-driven attempt | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-6** diagnosis is bounded by a profile-controlled attempt budget | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **FLOW-7** mutate applies surgical ApplyEdit operations with a reason and checkpoint | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-8** local_inspection runs zero-LLM checks and yields a typed outcome | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-9** per-node harness matrix is applied | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-10** per-node token budgets and a total guard are enforced | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **FLOW-11** oc-diagnostician exists and all nodes map to personas | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-12** the 12-skill oc_flow_default bundle is present and node-scoped | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-13** escalation produces a human handoff and stops code generation | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-14** consolidation finalizes the run with deltas and reindex | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-15** resume restores full OC Flow state or fails safe | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-16** opencontext run --workflow oc-flow executes OC Flow end to end | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-17** MCP tools and Studio render OC Flow live state | `04-oc-flow-architecture.md` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | DEFERRED |
| **FLOW-CONV** Fast/cheap/careful lane support | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-CONV** Runtime Brain decision integration + auto selection and SDD escalation | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `sdd-formal-feature` | PROPOSED |
| **FLOW-CONV** Bounded diagnosis | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-CONV** Surgical context retrieval (no SDD infra duplication) | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `sdd-formal-feature` | PROPOSED |
| **FLOW-CONV** Semantic cache use | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-CONV** Decision receipts | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **FLOW-CONV** Profile-aware behaviour + localized-bugfix benchmark | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-007-oc-flow` | `oc_flow/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |

## PR-008 Knowledge Graph v2

Change folder: `pr-008-kg-v2` · Source: `08-knowledge-graph-architecture.md` · 22 requirements (6 MET / 14 PROPOSED / 2 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **KG-01** SQLite-backed graph store with full-text search | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `indexing/graph_db.py` | `tests/core/test_graph_db.py` | `kg-retrieval-precision` | MET |
| **KG-02** Tree-sitter symbol and call-graph extraction across languages | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `indexing/tree_sitter_parser.py` | tbd | `kg-retrieval-precision` | MET |
| **KG-03** Incremental reindex with deterministic ids, prune, and staleness detection | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `knowledge_graph.py` | `tests/core/test_knowledge_graph.py` | `kg-retrieval-precision` | MET |
| **KG-04** Token-budgeted retrieval with omissions, confidence, and trust | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `retrieval/planner.py` | tbd | `context-token-efficiency` | MET |
| **KG-05** KgNode/KgEdge with 40 node and 20 edge kinds | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **KG-06** TemporalMetadata on facts that may change | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **KG-07** EvidenceRef v2 mandatory for non-structural facts | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **KG-08** GraphDelta model and apply_delta() | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **KG-09** KgQueryPlanner.plan(task, workflow, node, budget) | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **KG-10** Six named retrieval modes | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **KG-11** ContextSubgraph with node + token budgets, omissions, confidence | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **KG-12** Pluggable KnowledgeProvider interface | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **KG-13** Framework conventions and YAML/JSON/MD facts | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **KG-14** KG operations produce receipts and emit kg.* events | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **KG-15** Optional external graph-database backend via plugin | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | DEFERRED |
| **KG-16** Studio visualizes the relevant subgraph | `08-knowledge-graph-architecture.md` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | DEFERRED |
| **KG-CONV** Capability Graph linkage | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **KG-CONV** Organization Graph linkage | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **KG-CONV** Cache invalidation hooks | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **KG-CONV** KG freshness scoring | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-008-kg-v2` | `indexing/kg_freshness.py` | tbd | `kg-retrieval-precision` | MET |
| **KG-CONV** Graph confidence scoring | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-008-kg-v2` | `retrieval/contracts.py` | tbd | `kg-retrieval-precision` | MET |
| **KG-CONV** Graph query receipts | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-008-kg-v2` | `graph/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |

## PR-009 Memory v2

Change folder: `pr-009-memory-v2` · Source: `09-memory-architecture.md` · 22 requirements (6 MET / 14 PROPOSED / 2 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **MEM-009-01** Durable knowledge supersedes prior knowledge with lineage | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/graph.py` | tbd | `memory-usefulness` | MET |
| **MEM-009-02** Writes fold against active beliefs instead of accreting duplicates | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/consolidation.py` | tbd | `memory-usefulness` | MET |
| **MEM-009-03** New memory that contradicts existing memory is detected | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/contradictions.py` | tbd | `memory-usefulness` | MET |
| **MEM-009-04** Memory is operable via CLI verbs and MCP tools | `09-memory-architecture.md` | `pr-009-memory-v2` | `opencontext_cli/main.py` | tbd | `memory-usefulness` | MET |
| **MEM-009-05** Memory routes to backends by layer | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/composite.py` | tbd | `memory-usefulness` | MET |
| **MEM-009-06** Sensitive content is redacted/rejected before persistence | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/stores.py` | tbd | `policy-security` | MET |
| **MEM-009-07** MemoryRecord carries the full OC-MEMORY-001 §6 field set | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | PROPOSED |
| **MEM-009-08** MemoryCandidate carries proposer, evidence, expected reuse, confidence | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | PROPOSED |
| **MEM-009-09** Conflicts and write outcomes are typed and receipted | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | PROPOSED |
| **MEM-009-10** Memory backends satisfy the OC-MEMORY-001 §26 Protocol | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | PROPOSED |
| **MEM-009-11** The taxonomy covers the six OC-MEMORY-001 §5 memory types | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | PROPOSED |
| **MEM-009-12** Only the Memory Harness promotes candidates, via the ordered lifecycle | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | PROPOSED |
| **MEM-009-13** Curated `.opencontext/memory/*.md` summaries are generated | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | PROPOSED |
| **MEM-009-14** Retrieval is task-aware, budgeted, ordered, and observable | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **MEM-009-15** Runtime Intelligence uses memory for cost and selection | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | DEFERRED |
| **MEM-009-16** Memory is compressed before prompt injection by the Context Engine | `09-memory-architecture.md` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | DEFERRED |
| **MEM-CONV** Learning-loop integration | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | PROPOSED |
| **MEM-CONV** Memory quality score | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | PROPOSED |
| **MEM-CONV** Stale memory audit | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | PROPOSED |
| **MEM-CONV** Memory conflict reports | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | PROPOSED |
| **MEM-CONV** Profile-aware memory retrieval | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `kg-retrieval-precision` | PROPOSED |
| **MEM-CONV** No-chain-of-thought persistence checks | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-009-memory-v2` | `memory/ (new)` | tbd | `memory-usefulness` | PROPOSED |

## PR-010 Context Engine v2

Change folder: `pr-010-context-engine` · Source: `10-context-engineering-architecture.md` · 22 requirements (10 MET / 11 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **CTX-010-01** A single planner produces a traceable evidence plan for context | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `retrieval/planner.py` | tbd | `context-token-efficiency` | MET |
| **CTX-010-02** Selection trades relevance against redundancy | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `retrieval/planner.py` | tbd | `context-token-efficiency` | MET |
| **CTX-010-03** Packing respects a hard budget and records every omission | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `context/packing.py` | tbd | `context-token-efficiency` | MET |
| **CTX-010-04** Tokens are estimated deterministically and budgets are enforced | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `context/budgeting.py` | tbd | `context-token-efficiency` | MET |
| **CTX-010-05** Compression is multi-strategy, adaptive, and span-protecting | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `context/compression.py` | tbd | `context-token-efficiency` | MET |
| **CTX-010-06** Retrieved context carries evidence provenance and confidence | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `models/evidence.py` | tbd | `context-token-efficiency` | MET |
| **CTX-010-07** Retrieval prefers local evidence, KG, and symbols before files | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `retrieval/planner.py` | tbd | `kg-retrieval-precision` | MET |
| **CTX-010-08** Context is delivered as a typed L3/L2/L1 envelope | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `context/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **CTX-010-09** The harness selects among the seven book strategies per node | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `context/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **CTX-010-10** Budgets are scoped per workflow and per node | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `context/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **CTX-010-11** The Context Harness validates the envelope token_estimate | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `context/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **CTX-010-12** Compression keeps engineering meaning per an explicit taxonomy | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `context/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **CTX-010-13** Context is incrementally GC'd on defined triggers | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `context/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **CTX-010-14** Every retrieval emits query, budget, compression, and omission receipts | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `context/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **CTX-010-15** Five profiles tune retrieval, compression, and limits | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `context/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **CTX-010-16** Runtime Intelligence consumes context envelopes/receipts for cost and selection | `10-context-engineering-architecture.md` | `pr-010-context-engine` | `context/ (new)` | tbd | `context-token-efficiency` | DEFERRED |
| **CTX-CONV** Semantic cache | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-010-context-engine` | `context/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **CTX-CONV** Context routing strategies | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-010-context-engine` | `context/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **CTX-CONV** Context usefulness scoring | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-010-context-engine` | `context/ (new)` | tbd | `memory-usefulness` | PROPOSED |
| **CTX-CONV** Context omissions | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-010-context-engine` | `context/packing.py` | tbd | `context-token-efficiency` | MET |
| **CTX-CONV** Context receipts | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-010-context-engine` | `context/receipt.py` | tbd | `context-token-efficiency` | MET |
| **CTX-CONV** Prompt/context cache support | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-010-context-engine` | `context/prompt_cache.py` | tbd | `context-token-efficiency` | MET |

## PR-011 Runtime Intelligence

Change folder: `pr-011-runtime-intelligence` · Source: `11-runtime-intelligence-architecture.md` · 25 requirements (8 MET / 15 PROPOSED / 2 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **RI-011-01** Every run is represented by a trace with nested spans and events | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `models/trace.py` | tbd | `context-token-efficiency` | MET |
| **RI-011-02** Traces are persisted and reconstructable | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `trace/logger.py` | tbd | `context-token-efficiency` | MET |
| **RI-011-03** Token usage, timing, and cost are collected per operation | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `metrics.py` | `tests/core/test_metrics.py` | `context-token-efficiency` | MET |
| **RI-011-04** Cumulative token reduction is tracked over time | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `evaluation/telemetry.py` | `tests/core/test_telemetry.py` | `context-token-efficiency` | MET |
| **RI-011-05** A reproducible benchmark measures real context-build cost under a quality gate | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `evaluation/efficiency.py` | tbd | `context-token-efficiency` | MET |
| **RI-011-06** Comparison credits load-bearing capabilities honestly, not just tokens | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `evaluation/capability.py` | `tests/core/test_capability.py` | `context-token-efficiency` | MET |
| **RI-011-07** Runtime improvements are proposed from evidence, never silently applied | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `learning/evolution.py` | tbd | `context-token-efficiency` | MET |
| **RI-011-08** The runtime estimates cost before running and reconciles it against actuals | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-011-09** When workflow is auto, alternatives are compared and the choice is receipted | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-011-10** System-level confidence is computed across the eight runtime dimensions | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-011-11** Low confidence recommends a bounded action; the Runtime enforces it | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-011-12** A deterministic dry cognitive run predicts execution before running | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-011-13** The profiler attributes time/tokens to components and names bottlenecks | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-011-14** The full benchmark suite taxonomy and typed task/result schema exist | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-011-15** System self-health is exposed across the ten health dimensions | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-011-16** Promotion requires passing benchmarks and no first-run/token/security regression | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `first-run` | PROPOSED |
| **RI-011-17** Intelligence emits named events/receipts to the canonical telemetry layout | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-011-18** Studio surfaces cost, confidence, profiler, benchmark, and health views | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | DEFERRED |
| **RI-011-19** Cost/latency estimates consume real provider metrics | `11-runtime-intelligence-architecture.md` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | DEFERRED |
| **RI-CONV** Runtime Optimizer | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-CONV** Workflow what-if comparison | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-CONV** Confidence calibration | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-CONV** Cost calibration | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **RI-CONV** Token-savings attribution | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-011-runtime-intelligence` | `evaluation/telemetry.py` | `tests/core/test_telemetry.py` | `context-token-efficiency` | MET |
| **RI-CONV** Decision-quality metrics | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-011-runtime-intelligence` | `runtime/intelligence/ (new)` | tbd | `context-token-efficiency` | PROPOSED |

## PR-012 Provider & Model Gateway

Change folder: `pr-012-provider-gateway` · Source: `25-provider-model-gateway.md` · 21 requirements (8 MET / 11 PROPOSED / 2 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **PROV-012-01** The runtime drives every provider through one stable interface | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `llm/gateway.py` | tbd | `provider-fallback` | MET |
| **PROV-012-02** Roles select a model, not a hardcoded vendor | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `config.py` | `tests/core/test_config.py` | `provider-fallback` | MET |
| **PROV-012-03** No raw secret crosses the provider boundary | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `safety/firewall.py` | tbd | `policy-security` | MET |
| **PROV-012-04** Calls are bounded by a call budget and an output-token cap | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `operating_model/call_budget.py` | `tests/core/test_call_budget.py` | `context-token-efficiency` | MET |
| **PROV-012-05** No external provider is reached when policy forbids it | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `safety/provider_policy.py` | tbd | `policy-security` | MET |
| **PROV-012-06** Embeddings are produced behind a provider-neutral generator | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `embeddings/generators.py` | tbd | `provider-fallback` | MET |
| **PROV-012-07** Every provider call is time-bounded | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `providers/adapters.py` | `tests/core/test_adapters.py` | `provider-fallback` | MET |
| **PROV-012-08** One gateway composes routing → policy → prompt → adapter | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `policy-security` | PROPOSED |
| **PROV-012-09** Providers advertise capabilities and routing selects by capability | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `provider-fallback` | PROPOSED |
| **PROV-012-10** A configurable strategy governs provider selection | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `provider-fallback` | PROPOSED |
| **PROV-012-11** Failed calls fall back and retry within a limit, preserving contracts | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `provider-fallback` | PROPOSED |
| **PROV-012-12** Every provider call records cost/latency metrics | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `provider-fallback` | PROPOSED |
| **PROV-012-13** Provider lifecycle is observable via named events and receipts | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `provider-fallback` | PROPOSED |
| **PROV-012-14** Runtime Intelligence uses provider cost/latency for selection | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `provider-fallback` | DEFERRED |
| **PROV-012-15** Context budget/memory/KG/compression/contract and reranker/OCR/speech/image | `25-provider-model-gateway.md` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `context-token-efficiency` | DEFERRED |
| **PG-CONV** Provider capability model | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `provider-fallback` | PROPOSED |
| **PG-CONV** Provider cost model | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `provider-fallback` | PROPOSED |
| **PG-CONV** Provider policy redaction | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-012-provider-gateway` | `safety/firewall.py` | tbd | `policy-security` | MET |
| **PG-CONV** Structured-output validation | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `provider-fallback` | PROPOSED |
| **PG-CONV** Fallback receipts | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `provider-fallback` | PROPOSED |
| **PG-CONV** Provider cache integration | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-012-provider-gateway` | `providers/ (new)` | tbd | `provider-fallback` | PROPOSED |

## PR-013 CLI & MCP Modernization

Change folder: `pr-013-cli-mcp` · Source: `23-mcp-cli-adapter-architecture.md` · 26 requirements (5 MET / 20 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **CLI-013-01** Configuration uses the versioned v2 section envelope | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-013-02** balanced/low-cost/enterprise/research/performance profiles exist | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-013-03** Config resolves through the documented seven layers | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-013-04** Every run persists a reproducible config snapshot | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-013-05** `config doctor` validates the configuration actionably | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-013-06** The book's core CLI commands are reachable | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `main.py` | tbd | `first-run` | MET |
| **CLI-013-07** `opencontext run "task"` executes a workflow | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-013-08** `opencontext simulate "task"` previews a run without mutating | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-013-09** `session list\|status\|resume\|archive` operate over runtime sessions | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **CLI-013-10** `workflow explain` and `profile explain` describe behavior | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-013-11** Unified human/json/yaml/quiet/verbose output with actionable errors | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-013-12** Headless/CI operation is non-interactive and machine-readable | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `main.py` | tbd | `first-run` | MET |
| **CLI-013-13** `init` produces a usable config with minimal questions | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `main.py` | tbd | `first-run` | MET |
| **CLI-013-14** MCP exposes the runtime/KG/quality analysis tools | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `mcp_stdio.py` | `tests/core/test_mcp_stdio.py` | `first-run` | MET |
| **CLI-013-15** `opencontext_run` returns the full run contract, not counts | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-013-16** MCP exposes session step tools and workflow/profile/doctor tools | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-013-17** CLI and MCP share one Runtime API and public contracts | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-013-18** Studio visual control plane | `23-mcp-cli-adapter-architecture.md` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | DEFERRED |
| **CLI-CONV** `opencontext simulate "task"` dry-runs through the Runtime API | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-CONV** `opencontext doctor` emits actionable diagnostics | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-013-cli-mcp` | `opencontext_cli/main.py` | tbd | `first-run` | MET |
| **CLI-CONV** `opencontext workflow explain <id>` describes a workflow | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-CONV** `opencontext profile explain <id>` describes a profile | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-CONV** `opencontext decision-log` surfaces runtime decisions | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-CONV** `opencontext maturity assess` reports project maturity | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-CONV** `opencontext health` reports runtime health | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |
| **CLI-CONV** Improved `opencontext_run` MCP output through the Runtime API | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-013-cli-mcp` | `cli/ , mcp/ (new)` | tbd | `first-run` | PROPOSED |

## PR-014 Studio MVP

Change folder: `pr-014-studio` · Source: `22-studio-architecture.md` · 19 requirements (1 MET / 17 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **STU-014-01** `opencontext studio` starts a local read-only web control plane | `22-studio-architecture.md` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |
| **STU-014-02** Studio reads session artifacts/events/telemetry from `.opencontext/`, including historical sessions | `22-studio-architecture.md` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |
| **STU-014-03** A dashboard shows task, workflow, profile, status, current node, elapsed, cost, confidence, next action | `22-studio-architecture.md` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |
| **STU-014-04** A timeline shows nodes/phases, completion, current node, persona/skill bundle, failed gates, retries, escalation | `22-studio-architecture.md` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |
| **STU-014-05** A view shows the ContextEnvelope L1/L2/L3 layers, evidence refs, omissions, token budget, compression receipts | `22-studio-architecture.md` | `pr-014-studio` | `studio/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **STU-014-06** A view shows the relevant subgraph — files, symbols, tests, owners, dependencies, decisions, failure patterns | `22-studio-architecture.md` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |
| **STU-014-07** A view shows retrieved memory, candidates, promoted/rejected/superseded records, and conflict warnings | `22-studio-architecture.md` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |
| **STU-014-08** Views show changed files/diff/ApplyEdit ops/checksums/rollback + mutation receipts, and harness/gate results/warnings/failures/receipts/metrics | `22-studio-architecture.md` | `pr-014-studio` | `studio/ (new)` | tbd | `resume-rollback` | PROPOSED |
| **STU-014-09** Views show cost estimate vs actual, confidence report, workflow comparison/profiler, benchmark history and runtime-health trend | `22-studio-architecture.md` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |
| **STU-014-10** Studio surfaces config/profile and plugin state | `22-studio-architecture.md` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |
| **STU-014-11** Studio observes only — public contracts, evidence-backed visualizations, no mutation, runtime policy enforced | `22-studio-architecture.md` | `pr-014-studio` | `studio/ (new)` | tbd | `policy-security` | PROPOSED |
| **STU-014-12** Studio is optional; the runtime and all headless flows work without it | `22-studio-architecture.md` | `pr-014-studio` | `packages/opencontext_cli/opencontext_cli/main.py` | tbd | — | MET |
| **STU-014-13** Plugins may contribute Studio panels through the Plugin SDK, consuming public contracts only | `22-studio-architecture.md` | `pr-014-studio` | `studio/ (new)` | tbd | — | DEFERRED |
| **STU-CONV** Decision Log view | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |
| **STU-CONV** Runtime Brain / Scheduler view | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |
| **STU-CONV** Capability Graph view | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |
| **STU-CONV** Context budget view | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-014-studio` | `studio/ (new)` | tbd | `context-token-efficiency` | PROPOSED |
| **STU-CONV** Cache metrics view | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |
| **STU-CONV** Learning candidates view | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-014-studio` | `studio/ (new)` | tbd | — | PROPOSED |

## PR-015 Plugin SDK

Change folder: `pr-015-plugin-sdk` · Source: `12-plugin-extension-architecture.md` · 20 requirements (3 MET / 16 PROPOSED / 1 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **PR-015-MANIFEST** Typed PluginManifest with schema_version/id/requires/contributes | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PR-015-MANIFEST** Typed contributes-schema over the ~15 extension points | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PR-015-REGISTRY** PluginRegistry discovery, install and lifecycle management | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugin_system.py` | `tests/core/test_plugin_system.py` | `plugin-compatibility` | MET |
| **PR-015-REGISTRY** Full plugin lifecycle pipeline | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PR-015-CONTRACTS** Stable public contract per extension point | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PR-015-COMPAT** Enforced version compatibility; incompatible plugins disabled | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PR-015-PERMS** Explicit deny-by-default permissions | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugins/manifest.py` | tbd | `plugin-compatibility` | MET |
| **PR-015-PERMS** Full capability permission set | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PR-015-SANDBOX** Integrity verification and deny-by-default isolation | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugin_system.py` | `tests/core/test_plugin_system.py` | `plugin-compatibility` | MET |
| **PR-015-SANDBOX** Execution sandbox for untrusted plugin code | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PR-015-BENCH** Required plugin benchmark suite before activation | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PR-015-OBS** Plugin contributions are observable via events and receipts | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PR-015-ISOLATION** Plugins cannot modify Runtime Core or bypass policies, and failures are isolated | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PR-015-MARKET** Plugin marketplace publish/discovery/ratings | `12-plugin-extension-architecture.md` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | DEFERRED |
| **PLG-CONV** Execution-profile plugins | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PLG-CONV** Cache-provider plugins | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PLG-CONV** KG-provider plugins | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PLG-CONV** Memory-provider plugins | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PLG-CONV** Benchmark plugins | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PLG-CONV** Studio-panel plugins | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-015-plugin-sdk` | `plugins/ (new)` | tbd | `plugin-compatibility` | PROPOSED |

## PR-016 Marketplace

Change folder: `pr-016-marketplace` · Source: `31-marketplace-ecosystem-blueprint.md` · 21 requirements (9 MET / 9 PROPOSED / 3 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **PR-016-INST** Install from registry | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `plugin_system.py` | `tests/core/test_plugin_system.py` | — | MET |
| **PR-016-INST** Install from a GitHub release | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `plugin_system.py` | `tests/core/test_plugin_system.py` | — | MET |
| **PR-016-INST** Install from a direct URL | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `plugin_system.py` | `tests/core/test_plugin_system.py` | — | MET |
| **PR-016-INST** Configurable registry endpoint (local / private / official) | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `plugin_system.py` | `tests/core/test_plugin_system.py` | — | MET |
| **PR-016-DISC** Search the registry | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `plugin_system.py` | `tests/core/test_plugin_system.py` | — | MET |
| **PR-016-DISC** Inspect package details | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `commands/plugin_cmd.py` | tbd | — | MET |
| **PR-016-PKG** First-class marketplace package manifest (multi-asset bundle) | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `marketplace/ (new)` | tbd | — | PROPOSED |
| **PR-016-PKG** Download integrity verification (checksum + tamper-check) | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `plugin_system.py` | `tests/core/test_plugin_system.py` | — | MET |
| **PR-016-PKG** Cryptographic package signing & provenance verification | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `marketplace/ (new)` | tbd | — | PROPOSED |
| **PR-016-PKG** Compatibility enforced before activation | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `marketplace/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **PR-016-PUB** Publish flow with leak detection, validators, and versioning | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `marketplace/ (new)` | tbd | — | PROPOSED |
| **PR-016-TRUST** Source / provenance attribution recorded | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `plugin_system.py` | `tests/core/test_plugin_system.py` | — | MET |
| **PR-016-TRUST** Trust levels with policy gating | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `marketplace/ (new)` | tbd | `policy-security` | PROPOSED |
| **PR-016-TRUST** Package receipts (install / update / remove) | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `marketplace/ (new)` | tbd | — | PROPOSED |
| **PR-016-ECO** Ratings, hosted public registry & vendor publisher program | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `marketplace/ (new)` | tbd | — | DEFERRED |
| **PR-016-ECO** Studio marketplace panels & pre-activation benchmark | `31-marketplace-ecosystem-blueprint.md` | `pr-016-marketplace` | `marketplace/ (new)` | tbd | — | DEFERRED |
| **MKT-CONV** Package trust levels | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-016-marketplace` | `marketplace/ (new)` | tbd | — | PROPOSED |
| **MKT-CONV** Benchmark-on-install | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-016-marketplace` | `marketplace/ (new)` | tbd | — | DEFERRED |
| **MKT-CONV** Permission receipts | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-016-marketplace` | `marketplace/ (new)` | tbd | — | PROPOSED |
| **MKT-CONV** Private registry support | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-016-marketplace` | `plugin_system.py` | `tests/core/test_plugin_system.py` | — | MET |
| **MKT-CONV** Official framework packs | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-016-marketplace` | `marketplace/ (new)` | tbd | — | PROPOSED |

## PR-017 Benchmarks & Release

Change folder: `pr-017-benchmarks-release` · Source: `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` · 26 requirements (10 MET / 14 PROPOSED / 2 DEFERRED)

| Requirement | Source Doc | PR | Module | Test | Benchmark | Status |
|---|---|---|---|---|---|---|
| **REL-01** Automated test/lint/type/build CI with PyPI-token publish and artifact audit | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `operating_model/ai_leak.py` | tbd | `context-token-efficiency` | MET |
| **REL-02** Quality evaluator with a persisted regression baseline ratchet | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `quality/evaluator.py` | tbd | `(release gate suite)` | MET |
| **REL-03** A release-validation script with deterministic PASS/FAIL slots | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `benchmarks/` | tbd | `(release gate suite)` | MET |
| **REL-04** CON-vs-SIN efficiency benchmark with a persisted, claim-free report | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `evaluation/efficiency.py` | tbd | `(release gate suite)` | MET |
| **REL-05** Memory benchmark with recall/MRR/latency thresholds wired into release validation | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `memory/benchmark.py` | tbd | `kg-retrieval-precision` | MET |
| **REL-06** Every public contract carries a versioned schema_version | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `harness/models.py` | tbd | `(release gate suite)` | MET |
| **REL-07** Verify produces harness-report.json and compliance-matrix.json, enforced at archive | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `harness/models.py` | tbd | `(release gate suite)` | MET |
| **REL-08** A BenchmarkRunner over the named cognitive suites | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `(release gate suite)` | PROPOSED |
| **REL-09** Every benchmark report carries a suite name and semver version | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `(release gate suite)` | PROPOSED |
| **REL-10** CI runs a benchmark smoke gate on PR and the full suite nightly | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `(release gate suite)` | PROPOSED |
| **REL-11** The four DoD release gates computed against a stored baseline | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `(release gate suite)` | PROPOSED |
| **REL-12** compatibility_version + deprecated_since + stability level on every contract | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **REL-13** opencontext version plus config/kg/memory/session migration with dry-run and backups | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `(release gate suite)` | PROPOSED |
| **REL-14** Eval harness producing immutable evaluation records, with compare/report | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `(release gate suite)` | PROPOSED |
| **REL-15** Studio renders quality trends, benchmark deltas, and regression history | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `(release gate suite)` | DEFERRED |
| **REL-16** Release channels and scheduled large-repository benchmarks | `14-observability-benchmark-architecture.md / 21-testing-benchmark-strategy.md` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `(release gate suite)` | DEFERRED |
| **REL-CONV** First-run gate | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `first-run` | PROPOSED |
| **REL-CONV** OC Flow localized-bugfix gate | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `oc-flow-localized-bugfix` | PROPOSED |
| **REL-CONV** SDD formal-feature gate | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `sdd-formal-feature` | PROPOSED |
| **REL-CONV** Context token-efficiency gate | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-017-benchmarks-release` | `evaluation/efficiency.py` | tbd | `context-token-efficiency` | MET |
| **REL-CONV** KG retrieval-precision gate | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-017-benchmarks-release` | `evaluation/recall_eval.py` | `tests/core/test_recall_eval.py` | `kg-retrieval-precision` | MET |
| **REL-CONV** Memory-usefulness gate | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-017-benchmarks-release` | `memory/benchmark.py` | tbd | `memory-usefulness` | MET |
| **REL-CONV** Policy/security gate | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `policy-security` | PROPOSED |
| **REL-CONV** Plugin-compatibility gate | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `plugin-compatibility` | PROPOSED |
| **REL-CONV** Provider-fallback gate | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `provider-fallback` | PROPOSED |
| **REL-CONV** Resume/rollback gate | `OC-FINAL-CONVERGENCE-001.md §6` | `pr-017-benchmarks-release` | `benchmarks/ (new)` | tbd | `resume-rollback` | PROPOSED |

---

## Orphan check

Every one of the **453** requirements above originates in exactly one `spec.md` under exactly one `.sdd/changes/pr-*/` change folder, so each maps to **exactly one PR** — there are no orphaned, duplicated, or unassigned requirements. Convergence patch requirements (the `*-CONV` SPEC sections, traced to `OC-FINAL-CONVERGENCE-001.md` §6) are folded into their owning PR's spec rather than a separate change, preserving the one-requirement-to-one-PR invariant required by `57-final-1-0-acceptance-gates.md` §D ("No orphans").
