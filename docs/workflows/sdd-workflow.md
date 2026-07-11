# Specification-Driven Development (SDD) Workflow

SDD is OpenContext's default workflow for non-trivial changes. Nine phases. Full traceability. Quality gates at every step. Works offline with any agent.

## Overview

```
explore → propose → spec → design → tasks → apply → verify → review → archive
```

The harness runner executes phases in sequence (or in parallel where dependencies allow), persists artifacts, evaluates gates, and builds memory from outcomes. The agent does the work; the harness ensures nothing ships without passing verification.

### Key Principles

1. **Contract first** — every run starts with a ContextContract (known / unknown / must verify)
2. **Minimum sufficient context** — the agent receives only what the task requires, verified by the graph
3. **Governed** — 15 quality gates at verify; no archive without passing them
4. **Traceable** — every run produces ledgers, gates, artifacts, and memory records
5. **Learns** — failures update the memory graph; future similar tasks benefit from past mistakes

## Three Ways to Run SDD

### 1. Interactive loop (recommended)

```bash
opencontext loop --task "Add OAuth2 login" --flow full
```

User checkpoints after each phase. Press `Y` to continue, `n` to abort.

### 2. Autonomous loop

```bash
opencontext loop --task "Add OAuth2 login" --flow autonomous
```

No prompts. Gates decide whether to continue. Suitable for CI/CD.

### 3. Harness directly

```bash
opencontext harness run --workflow sdd --task "Add OAuth2 login"
opencontext harness run --workflow sdd --task "..." --json    # CI-friendly
```

## The Nine Phases

### explore

**What happens:**
1. Index project (incremental)
2. Query memory (PROCEDURAL + FAILURE layers) for relevant past learnings
3. Build ContextContract: classify task → determine risk tier → populate known/unknown/gates
4. Plan context retrieval (budget, strategy, expansion rounds)
5. Retrieve from knowledge graph + memory, score with 9 signals, pack
6. Persist `contract.yaml` as artifact

**Outputs:** context pack, `contract.yaml`  
**Gates:** `project-index-exists`, `context-pack-created`, `token-budget`

### propose

**What happens:**
- Classify task type and risk tier
- Produce compressed summary of what will change and why
- Include ContextContract summary (minus detailed evidence)

**Outputs:** `proposal.json`

### spec

**What happens:**
- Write formal requirements as scenarios
- Every scenario is testable and verifiable

**Outputs:** `spec.yaml`

### design

**What happens:**
- Architecture decisions and implementation approach
- Can run in parallel with spec (no dependency between them)

**Outputs:** `design.yaml`

### tasks

**What happens:**
- Break spec+design into ordered implementation checklist
- Each task maps to a concrete code change

**Outputs:** `tasks.yaml`

### apply

**What happens:**
- Execute changes according to tasks
- Agent (or user) applies code changes
- Apply manifest records what changed

**Outputs:** `apply-manifest.json`  
**Gates:** `approval-required-for-writes`, `no-high-risk-exports`

### verify

**What happens:**
1. Run the test suite (a ContextContract `must_verify` item)
2. Run lint + type-check
3. Run the security scan (secret patterns) — the `security-scan-passed` gate
4. Run mutation analysis if enabled (contract `must_verify`, reported in `gates.json`)
5. Evaluate all 15 quality gates

Verification is driven by the run's ContextContract `must_verify` items and the harness gates, executed by the configured tools/executors — not by dedicated local agents.

**Outputs:** `verify-report.json`  
**Gates:** All 15 (see [Quality Gates](../quality/quality-gates.md))

### review

**What happens:**
- Aggregate all run artifacts, ledgers, and gate outcomes into a human- and machine-readable review of what was produced

**Outputs:** `review.json`  
**Gates:** `review_artifact_created`

### archive

**What happens:**
1. Harvest memory via `MemoryHarvester`:
   - Episodic record of what happened
   - Procedural rules extracted from failures
   - Failure patterns linked to symbols in the graph
2. Add trace node to UnifiedGraph
3. Finalize run directory
4. Clear WORKING memory layer

**Outputs:** `run.json`, memory records, updated failure graph

## Flow Tracks

| Track | Phases | Token budget | Use for |
|-------|--------|-------------|---------|
| `quick` | explore → apply → verify | Tier-based | Simple fixes, renames, trivial changes |
| `standard` | explore → spec+design → apply → verify | Tier-based | Features, refactors |
| `full` | All 9 phases | Tier-based | Architecture, security, migrations |
| `autonomous` | All 9, no prompts | Tier-based | CI/CD, scripts |

## Risk Tiers

Automatically assigned by `TaskClassifier` + `RiskClassifier`:

| Tier | Token budget | Compression | When |
|------|-------------|-------------|------|
| `cheap` | 8,000 | terse | Docs, renames, trivial fixes |
| `precise` | 16,000 | compact | Features, refactors |
| `critical` | 28,000 | none | Security, migrations, breaking changes |

Security tasks are always `critical`. Migration tasks are always `critical`.

## TDD Integration

The harness enforces red→green→refactor at verify:

```bash
opencontext preset apply strict-tdd
opencontext loop --task "add feature X" --flow full
# → VERIFY blocks apply if no failing test was written first
```

With `strict-tdd`, the `FailingTestExistsGate` must pass before apply is allowed to run.

## Mutation Testing

```yaml
# opencontext.yaml
testing:
  mutation:
    enabled: true
    threshold: 80
    fail_on_low_score: false
```

When enabled, mutation analysis runs at verify as a contract `must_verify` item. Score below threshold:
- `fail_on_low_score: false` → WARNING (default)
- `fail_on_low_score: true` → blocks archive

```bash
opencontext mutation run --scope changed --threshold 80
```

## Phase Dependencies (DAG)

```
explore
  └─ propose
       └─ spec ─┐
       └─ design ┤
                 └─ tasks
                      └─ apply
                           └─ verify
                                └─ review
                                     └─ archive
```

spec and design run in parallel (both depend only on propose).

## Run Artifacts

All artifacts written to `.opencontext/runs/<run_id>/`:

| File | Contents |
|------|----------|
| `contract.yaml` | ContextContract: known/unknown/must_verify |
| `proposal.json` | Task classification and change approach |
| `spec.yaml` | Formal requirements and scenarios |
| `design.yaml` | Architecture decisions |
| `tasks.yaml` | Ordered implementation checklist |
| `apply-manifest.json` | What changed |
| `verify-report.json` | Tests, mutation score, all 15 gate results |
| `review.json` | Aggregated artifacts, ledgers, and gate outcomes |
| `memory-harvest.json` | Memory records created at archive |
| `run.json` | Run metadata, phase summaries, final status |

## Phase Dependency Ordering (Orchestrator)

```python
PHASE_DEPENDENCIES = {
    "explore": [],
    "propose": ["explore"],
    "spec": ["propose"],
    "design": ["propose"],
    "tasks": ["spec", "design"],
    "apply": ["tasks"],
    "verify": ["apply"],
    "review": ["verify"],
    "archive": ["review"],
}
```

## Examples

```bash
# Python/Django — full workflow
opencontext loop --task "Create user registration endpoint" --flow full

# Node.js — quick fix
opencontext loop --task "Fix typo in error message" --flow quick

# Architecture change — autonomous (CI)
opencontext loop --task "Migrate auth from JWT to session tokens" --flow autonomous

# Maximum compression (large output)
opencontext loop --task "..." --flow standard --compress efficient

# Retry up to 3 times on verify failure
opencontext loop --task "..." --flow full --max-rounds 3
```

## See Also

- [Controlled Agentic Harness](../concepts/controlled-agentic-harness.md)
- [Quality Gates](../quality/quality-gates.md)
- [Memory System](../memory/overview.md)
- [Compression](../token-efficiency/compression.md)
- [Custom Workflows](./custom-workflows.md)
