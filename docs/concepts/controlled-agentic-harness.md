# Controlled Agentic Harness

The harness is OpenContext's execution backbone. Every agent action, phase transition, and quality gate runs through it. It enforces deny-by-default permissions, token budgets, and full traceability.

## What the Harness Does

The harness wraps every phase of the SDD workflow with:

- **Token budget enforcement** — each phase has a hard cap; overage warns or fails
- **Quality gates** — 15 gates evaluated at verify (tests, lint, security, secrets, omissions...)
- **Artifact persistence** — every phase writes auditable YAML/JSON to `.opencontext/runs/`
- **Memory integration** — ExplorePhase builds a ContextContract; ArchivePhase harvests memory
- **Permission model** — writes require explicit approval; network calls are denied by default

## The Five-Agent Loop

The harness orchestrates five built-in agents, each in the right mode:

| Agent | Mode | Runs at |
|-------|------|---------|
| `context-planner` | Local | Explore |
| `tdd-enforcer` | Local | Verify |
| `mutation-analyst` | Local | Verify (if enabled) |
| `security-audit` | Local | Verify |
| `code-review` | Hybrid | Review |

Local agents run pure Python — no LLM, no API key. The `code-review` agent does graph analysis locally and emits a structured prompt for the host LLM to execute.

## Phases

Eight phases, each producing artifacts and passing through gates:

```
explore → propose → spec → design → tasks → apply → verify → archive
```

| Phase | Key Actions | Artifacts |
|-------|-------------|-----------|
| explore | Index project, build ContextContract, query memory | `contract.yaml`, context pack |
| propose | Classify task, plan approach, compressed summary | `proposal.json` |
| spec | Write formal requirements and scenarios | `spec.yaml` |
| design | Architecture decisions and approach | `design.yaml` |
| tasks | Break into ordered implementation checklist | `tasks.yaml` |
| apply | Execute changes with agent | `apply-manifest.json` |
| verify | Tests + lint + type-check + mutation + 15 gates | `verify-report.json` |
| archive | Harvest memory, link failure graph, finalize | `run.json`, memory records |

## ContextContract

Every explore phase produces a ContextContract — the auditable specification for what the agent will receive:

```yaml
task: fix crash in auth middleware
task_type: bugfix
risk_tier: critical
token_budget: 28000
known:
  - source: src/auth/middleware.py
    confidence: 1.0
    verified: true
unknown:
  - exact failing method
must_verify:
  - id: run-tests
  - id: security-scan
```

Risk tiers map to token budgets:
- `cheap` → 8,000 tokens (docs, renames, trivial fixes)
- `precise` → 16,000 tokens (features, refactors)
- `critical` → 28,000 tokens (security, migrations, breaking changes)

## Quality Gates (15)

All gates run at verify. Status: `passed` / `warning` / `failed`.

| Gate | What it checks |
|------|---------------|
| `project-index-exists` | Knowledge graph indexed |
| `context-pack-created` | Context delivered to agent |
| `token-budget` | Pack within tier budget |
| `run-tests` | Test suite passes |
| `lint` | Zero lint errors |
| `type-check` | Zero type errors |
| `security-scan` | No secret patterns |
| `no-secret-leakage` | Context pack clean |
| `included-sources-present` | Required symbols in pack |
| `omissions-recorded` | Omissions documented |
| `provider-policy-passed` | Provider rules satisfied |
| `approval-required-for-writes` | Writes confirmed |
| `no-high-risk-exports` | No confidential data to external providers |
| `review-artifact-created` | Review trail exists |
| `artifact-persisted` | Artifacts saved to disk |

## Budget Modes

| Mode | Behavior |
|------|----------|
| `off` | No enforcement |
| `warn` | Log warnings (default) |
| `strict` | Fail on overage — blocks apply |

```bash
opencontext harness run --workflow sdd --task "..." --budget-mode strict
```

## Invoking the Harness

```bash
# Full 8-phase workflow
opencontext harness run --workflow sdd --task "Add rate limiting"

# Via the interactive loop
opencontext loop --task "Add rate limiting" --flow full

# Via the loop, autonomous (no user prompts)
opencontext loop --task "Add rate limiting" --flow autonomous

# CI-friendly JSON output
opencontext harness run --workflow sdd --task "..." --json
```

## Run Artifacts

Each run writes to `.opencontext/runs/<run_id>/`:

```
run.json              # Run metadata and summary
contract.yaml         # ContextContract from explore
proposal.json         # Change proposal
apply-manifest.json   # What was changed and why
verify-report.json    # Tests, mutation score, gate results
review.json           # Aggregated phase data
memory-harvest.json   # Memory records created at archive
```

## Permission Model

Native tool execution is disabled by default. The harness planner evaluates every tool call against:

- Allowlist / deny rules
- Read-only vs write capability flags
- Network egress policy (`external_providers_enabled`)
- Human approval requirements for writes

Writes to files, external APIs, or any system boundary require explicit approval unless `approval_required_for_writes` is disabled in config.

## Related

- [SDD Workflow](../workflows/sdd-workflow.md)
- [Agentic Loop](../workflows/modes.md)
- [Quality Gates](../quality/quality-gates.md)
- [Memory System](../memory/overview.md)
