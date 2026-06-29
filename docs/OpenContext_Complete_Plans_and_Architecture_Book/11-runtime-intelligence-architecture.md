# OpenContext Runtime Intelligence Architecture
## Version 1.0 (Draft)
### Document ID
OC-RUNTIME-INTELLIGENCE-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`
- `02-runtime-architecture.md`
- `08-knowledge-graph-architecture.md`
- `09-memory-architecture.md`
- `10-context-engineering-architecture.md`

---

# 1. Purpose

This document defines the Runtime Intelligence Architecture for OpenContext.

Runtime Intelligence is the layer that observes, measures, estimates, explains and improves the OpenContext Runtime.

It does not execute workflows directly.

It informs workflow selection, cost estimation, confidence scoring, simulation, profiling, benchmarking, health checks and evolution proposals.

Runtime Intelligence turns OpenContext from an execution engine into a learning engineering platform.

---

# 2. Mission

Runtime Intelligence exists to answer:

- Which workflow should be used?
- What will this task probably cost?
- How confident is the runtime?
- Which subsystem is the bottleneck?
- Which harness caused failure?
- Which memory is stale?
- Which skill is underperforming?
- Which workflow would have been cheaper?
- Which runtime improvement is justified by evidence?

---

# 3. Core Principles

1. Measure before optimizing.
2. Estimate before executing.
3. Explain every major decision.
4. Benchmark every runtime change.
5. Never self-modify without evidence.
6. Prefer recommendations over silent behaviour changes.
7. Track cost and correctness together.
8. Confidence must affect execution.
9. Health must be visible.
10. Evolution must be reversible.

---

# 4. Position in the Architecture

```text
Runtime
  -> Runtime Intelligence
    -> Cost Engine
    -> Confidence Engine
    -> Simulator
    -> Profiler
    -> Benchmark System
    -> Runtime Health
    -> Evolution Engine
```

Runtime Intelligence consumes:

- events
- traces
- artifacts
- receipts
- KG data
- memory records
- benchmark results
- policy decisions
- provider metrics

Runtime Intelligence produces:

- estimates
- confidence reports
- simulation reports
- recommendations
- benchmark reports
- evolution candidates
- health reports

---

# 5. Components

```text
runtime_intelligence/
  cost.py
  confidence.py
  simulator.py
  profiler.py
  benchmarks.py
  health.py
  evolution.py
  recommendations.py
  reports.py
```

---

# 6. Cost Engine

## Purpose

Estimate and record execution cost.

Cost includes:

- input tokens
- output tokens
- tool calls
- local command time
- provider latency
- retries
- diagnosis attempts
- context retrieval
- inspection time

## CostEstimate

```python
class CostEstimate(BaseModel):
    workflow: str
    lane: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_tool_calls: int
    estimated_duration_s: int
    estimated_cost_usd: float | None
    confidence: float
    assumptions: list[str]
```

## CostReport

```python
class CostReport(BaseModel):
    session_id: str
    run_id: str
    estimate: CostEstimate
    actual_input_tokens: int
    actual_output_tokens: int
    actual_tool_calls: int
    actual_duration_s: int
    estimate_error_pct: float
    cost_by_component: dict[str, Any]
    token_savings: dict[str, int]
```

---

# 7. Workflow Cost Comparison

When workflow is `auto`, the runtime should compare alternatives.

Example:

```json
{
  "oc-flow": {
    "estimated_tokens": 6200,
    "estimated_success": 0.84,
    "estimated_duration_s": 45
  },
  "sdd": {
    "estimated_tokens": 18000,
    "estimated_success": 0.92,
    "estimated_duration_s": 180
  }
}
```

The selected workflow decision must be stored as a receipt.

---

# 8. Confidence Engine

## Purpose

Calculate confidence across runtime dimensions.

Confidence is not model certainty.

It is system-level confidence based on evidence.

## Dimensions

```text
intent_confidence
context_confidence
plan_confidence
mutation_confidence
inspection_confidence
memory_confidence
security_confidence
overall_confidence
```

## ConfidenceReport

```python
class ConfidenceReport(BaseModel):
    session_id: str
    run_id: str
    workflow: str
    dimensions: dict[str, float]
    overall: float
    threshold: float
    recommended_action: str
    evidence_refs: list[str]
```

---

# 9. Confidence Actions

When confidence drops, Runtime Intelligence may recommend:

- continue
- retrieve deeper context
- ask clarification
- switch workflow
- enter deep mode
- require approval
- escalate

The Runtime enforces the final decision.

Runtime Intelligence recommends; Runtime governs.

---

# 10. Runtime Simulator

## Purpose

Predict execution before running.

The simulator performs a dry cognitive run:

- expected workflow
- expected lane
- expected files
- expected risks
- expected tests
- expected cost
- expected confidence

## SimulationReport

```python
class SimulationReport(BaseModel):
    task: str
    recommended_workflow: str
    recommended_lane: str
    expected_files: list[str]
    expected_symbols: list[str]
    expected_tests: list[str]
    risk_flags: list[str]
    cost_estimates: list[CostEstimate]
    confidence_estimate: float
    recommendation: str
```

---

# 11. Runtime Profiler

## Purpose

Find bottlenecks.

Profiler output should explain where time and tokens are spent.

Example:

```text
Context retrieval: 38%
Diagnosis: 31%
Planning: 14%
Mutation: 8%
Inspection: 5%
Consolidation: 4%
```

## ProfilerReport

```python
class ProfilerReport(BaseModel):
    session_id: str
    run_id: str
    cost_by_component: dict[str, Any]
    bottlenecks: list[str]
    recommendations: list[str]
```

---

# 12. Benchmark System

## Purpose

Validate runtime quality with repeatable tests.

Benchmark categories:

- first-run
- bugfix
- feature
- SDD
- OC Flow
- KG retrieval
- memory retrieval
- compression
- skill
- persona
- harness
- security
- framework-specific

## BenchmarkTask

```python
class BenchmarkTask(BaseModel):
    id: str
    name: str
    repo_fixture: str
    task: str
    expected_workflow: str | None
    setup_commands: list[str]
    eval_commands: list[str]
    success_criteria: list[str]
    max_tokens: int | None
    max_changed_lines: int | None
```

## BenchmarkResult

```python
class BenchmarkResult(BaseModel):
    task_id: str
    success: bool
    tokens: int
    duration_s: int
    tool_calls: int
    changed_files: int
    changed_lines: int
    tests_passed: bool
    security_passed: bool
    notes: str
```

---

# 13. Runtime Health

## Purpose

Expose the health of the system itself.

Health dimensions:

- KG freshness
- memory quality
- skill catalog health
- harness pass rate
- workflow selector accuracy
- cost estimator calibration
- confidence calibration
- benchmark trend
- policy violations
- context drift

## RuntimeHealthReport

```python
class RuntimeHealthReport(BaseModel):
    overall_score: float
    dimensions: dict[str, float]
    critical_findings: list[str]
    recommendations: list[str]
```

---

# 14. Evolution Engine

## Purpose

Propose evidence-backed improvements to OpenContext.

The Evolution Engine may propose changes to:

- skill prompts
- skill routing
- persona contracts
- harness config
- workflow selector thresholds
- context retrieval policies
- compression policies
- cost estimator weights
- confidence thresholds

It must not silently apply unsafe changes.

## EvolutionCandidate

```python
class EvolutionCandidate(BaseModel):
    candidate_id: str
    target_type: str
    target_id: str
    change_summary: str
    rationale: str
    expected_benefit: str
    risks: list[str]
    generated_from_runs: list[str]
    required_benchmarks: list[str]
```

---

# 15. Evolution Promotion Rules

A candidate may be promoted only if:

- required benchmarks pass;
- first-run benchmark does not regress;
- token cost does not worsen beyond threshold;
- security benchmark does not regress;
- human approval is present if required;
- rollback path exists.

---

# 16. Runtime Intelligence Events

Required events:

- intelligence.cost.estimated
- intelligence.cost.reported
- intelligence.confidence.calculated
- intelligence.simulation.created
- intelligence.profiler.reported
- intelligence.health.reported
- intelligence.evolution_candidate.created
- intelligence.evolution_candidate.promoted
- intelligence.evolution_candidate.rejected

---

# 17. Runtime Intelligence Receipts

Required receipts:

- workflow comparison receipt
- cost estimate receipt
- confidence decision receipt
- simulation receipt
- benchmark receipt
- evolution proposal receipt

---

# 18. Configuration

```yaml
runtime_intelligence:
  enabled: true

  cost:
    estimate_before_run: true
    show_workflow_comparison: true
    track_actual: true

  confidence:
    enabled: true
    ask_below: 0.65
    deep_mode_below: 0.75
    switch_workflow_below: 0.55

  simulator:
    enabled: true
    run_for_auto_workflow: true

  benchmarks:
    enabled: true
    first_run_suite: true
    run_on_runtime_changes: true

  evolution:
    enabled: true
    mode: propose_only
    require_benchmarks: true
    require_approval: true

  health:
    enabled: true
```

---

# 19. Studio Integration

OpenContext Studio should display:

- workflow cost estimate;
- actual cost;
- token savings;
- confidence dimensions;
- workflow comparison;
- profiler breakdown;
- benchmark trends;
- runtime health;
- evolution proposals.

Studio must make runtime intelligence understandable to users.

---

# 20. Relationship with SDD

Runtime Intelligence improves SDD by:

- estimating cost before formal workflow;
- validating when SDD is justified;
- measuring phase costs;
- identifying planning bottlenecks;
- benchmarking spec/design/task generation;
- recommending profile changes.

---

# 21. Relationship with OC Flow

Runtime Intelligence improves OC Flow by:

- choosing quick/fast/full lane;
- limiting diagnosis token burn;
- switching to SDD when scope grows;
- detecting low confidence;
- measuring local-first effectiveness;
- learning from repeated bugfixes.

---

# 22. Migration from Current Branch

Migration steps:

1. Preserve existing event/warning data.
2. Add cost accounting to current run summaries.
3. Add workflow selection receipts.
4. Add confidence report scaffold.
5. Add profiler report from existing phase durations.
6. Add benchmark task schema.
7. Add runtime health command.
8. Add evolution candidate model.
9. Integrate with Studio later.

---

# 23. Invariants

1. Runtime Intelligence recommends; Runtime governs.
2. Evolution proposals require evidence.
3. Benchmarks gate promotion.
4. Cost and confidence are recorded.
5. Estimates are compared to actuals.
6. First-run benchmark must not regress.
7. Security benchmarks must not regress.
8. Studio visualizes intelligence but does not own execution.
9. No self-modification without approval.
10. Runtime Intelligence is optional but first-class.

---

# 24. Definition of Done

Runtime Intelligence is implemented when:

- cost estimates exist;
- actual cost reports exist;
- confidence reports exist;
- workflow comparison works;
- simulator works;
- profiler works;
- benchmark system exists;
- runtime health report exists;
- evolution candidates can be proposed;
- Studio can visualize intelligence reports;
- decisions are recorded as receipts.

---

# 25. Final Statement

Runtime Intelligence is how OpenContext improves.

The runtime should not merely execute.

It should measure itself, explain itself and evolve through evidence.
