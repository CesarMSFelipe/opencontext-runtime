# Controlled Agentic Harness

The harness is OpenContext's execution backbone. Every agent action, phase transition, and quality gate runs through it. It enforces deny-by-default permissions, token budgets, and full traceability.

## What the Harness Does

The harness wraps every phase of the SDD workflow with:

- **Token budget enforcement** — each phase has a hard cap; overage warns or fails
- **Quality gates** — quality gates (15) evaluated across phases (tests, lint, security, secrets, omissions...)
- **Artifact persistence** — every phase writes auditable YAML/JSON to `.opencontext/runs/`
- **Memory integration** — ExplorePhase builds a ContextContract; ArchivePhase harvests memory
- **Permission model** — writes require explicit approval; network calls are denied by default

## How Verification Runs

The harness does not run dedicated local agents. Each phase runs through a wired executor (`run_phase_executor` in `harness/phases.py`) — the host's AI agent, or a registered executor — and its output is checked against the phase's gates. When no executor is wired, a work-producing phase reports a WARNING scaffold instead of pretending it ran.

Verification itself is driven by two mechanisms:

- **ContextContract `must_verify` items** — each run's contract lists the checks that must pass for its risk tier (e.g. run-tests, security-scan, mutation), resolved from `contract.py` `TIER_GATES`. These are executed by the configured tools/executors, not by local agent classes.
- **PhaseGates** — the harness-level gates (see [Quality Gates](#quality-gates)) that guard each phase transition and block archive when they fail.

Local, deterministic checks (secret scanning, budget, artifact persistence) run in pure Python — no LLM, no API key. Work that needs generation (proposals, code, review narratives) is delegated to the wired executor / host LLM.

## Phases

Nine phases, each producing artifacts and passing through gates:

```
explore → propose → spec → design → tasks → apply → verify → review → archive
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
| review | Aggregate phase artifacts, ledgers, and gate outcomes | review.json |
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

## Quality Gates

Gates run at the phase they apply to — e.g. project-index-exists/context-pack-created at explore, trace-id/omissions at propose, approval/failing-test at apply, security-scan at verify, review-artifact at review, artifact-persisted at archive; token-budget runs at every phase. Status: `passed` / `warning` / `failed`.

| Gate | What it checks |
|------|---------------|
| `project-index-exists` | Knowledge graph indexed |
| `context-pack-created` | Context delivered to agent |
| `token-budget` | Pack within tier budget |
| `trace-id-created` | Trace ID generated for the run |
| `failing-test-exists` | A failing test exists before apply — Strict TDD |
| `security-scan-passed` | No secret patterns |
| `no-secret-leakage` | Context pack clean |
| `included-sources-present` | Required symbols in pack |
| `omissions-recorded` | Omissions documented |
| `provider-policy-passed` | Provider rules satisfied |
| `approval-required-for-writes` | Writes confirmed |
| `no-high-risk-exports` | No confidential data to external providers |
| `review-artifact-created` | Review trail exists |
| `review-warnings` | Warnings surfaced at review |
| `artifact-persisted` | Artifacts saved to disk |

Note: `run-tests`, `lint`, and `type-check` are ContextContract `must_verify` items per risk tier (contract.py TIER_GATES), not harness PhaseGates.

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
# Full 9-phase workflow
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
verify-report.json    # Test results and summary
review.json           # Aggregated phase data
gates.json            # Per-phase gate results (incl. mutation-tests when enabled)
memory_delta.json     # Memory records created at archive
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
