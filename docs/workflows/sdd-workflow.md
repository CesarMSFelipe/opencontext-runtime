# Specification-Driven Development (SDD) Workflow

The SDD workflow is OpenContext's 6-phase specification-driven development lifecycle, powered by the **harness runner**. It moves from exploration through proposal, implementation, verification, and review, with full traceability and governance via phase gates.

## Overview

SDD is designed to be **technology-agnostic**, **provider-neutral**, and **agent-composable**. The harness runner executes phases in sequence, evaluates gates (token budget, artifact persistence, project index, etc.), and persists results to `.opencontext/runs/<run_id>/`.

### Key Principles

1. **Specification-First**: Define intent, scope, and approach before implementation
2. **Governed**: Each phase passes through gates (budget, persistence, security)
3. **Traceable**: Every run produces ledgers, gates, and artifacts
4. **Provider-Neutral**: No API calls — works offline with mock provider

## The Harness Workflow Phases

The harness runner executes six phases:

```
Explore → Propose → Apply → Verify → Review → Archive
```

### 1. Explore

**Purpose**: Index the project and build a context pack for the task.

- Reads project structure, files, and symbols
- Builds a compact context pack within the token budget
- Checks: project index exists, context pack created, token budget

**CLI**:
```bash
opencontext harness run --workflow explore-only --task "How does authentication work?"
```

**Produces**: Indexed manifest, context pack, and token ledger.

### 2. Propose

**Purpose**: Create a structured SDD change proposal from the exploration results.

- Defines what will change and why
- Outlines the approach and scope
- Persists proposal to `proposal.json`

**CLI**:
```bash
opencontext harness run --workflow sdd --task "Implement OAuth2 support"
```

**Produces**: `proposal.json` with task, scope, and approach metadata.

### 3. Apply

**Purpose**: Apply changes as defined in the proposal.

- Creates an apply manifest tracking what was applied
- Records change metadata for auditability

**CLI**: Part of the full SDD workflow (`--workflow sdd`).

**Produces**: `apply-manifest.json` with change summary.

### 4. Verify

**Purpose**: Run tests and validate the implementation.

- Executes `pytest` in the project root
- Captures test output, exit code, pass/fail counts
- Reports warnings on test failures

**CLI**: Part of the full SDD workflow (`--workflow sdd`).

**Produces**: `verify-report.json` with test results and exit code.

### 5. Review

**Purpose**: Aggregate phase results and produce a review summary.

- Collects ledgers, gates, artifacts, and warnings from all prior phases
- Reports gate pass/fail counts and warnings

**CLI**: Part of the full SDD workflow (`--workflow sdd`).

**Produces**: `review.json` with aggregated phase data and gate statistics.

### 6. Archive

**Purpose**: Persist run artifacts and verify persistence.

- Confirms `run.json` was saved to disk
- Finalizes the run directory

**CLI**: Part of the full SDD workflow (`--workflow sdd`).

**Produces**: Archived run directory under `.opencontext/runs/<run_id>/`.

## Available Workflows

```bash
opencontext harness list
```

| Workflow | Phases | Description |
|----------|--------|-------------|
| `sdd` | explore → propose → apply → verify → review → archive | Full SDD lifecycle |
| `explore-only` | explore | Project indexing and context pack |
| `apply-only` | apply → verify → archive | Apply then verify and archive |

## Budget Modes

The harness supports three token budget enforcement modes:

| Mode | Behavior |
|------|----------|
| `off` | No budget enforcement |
| `warn` | Log warnings when tokens exceed budget (default) |
| `strict` | Fail the run and exit with code 1 on overage |

```bash
opencontext harness run --workflow sdd --task "my task" --budget-mode strict
```

## Complete SDD Flow

Run all six phases in sequence:

```bash
opencontext harness run --workflow sdd --task "Implement OAuth2 authentication" --budget-mode warn
```

Output:
```
Harness Run: sdd-a1b2c3d4e5f6
  Workflow: sdd
  Task: Implement OAuth2 authentication
  Status: passed
  Phases: 6
    explore: 599/6000 tokens — passed
    propose: 0/6000 tokens — passed
    apply: 0/6000 tokens — passed
    verify: 0/4000 tokens — passed
    review: 0/4000 tokens — passed
    archive: 0/2000 tokens — passed
  Gates: 10
  Trace IDs: 0
```

For JSON output (CI-friendly):
```bash
opencontext harness run --workflow sdd --task "my task" --json
```

## Run Artifacts

Each harness run creates a directory under `.opencontext/runs/<run_id>/`:

| File | Contents |
|------|----------|
| `run.json` | Run metadata (id, workflow, status, created_at) |
| `ledger.json` | Per-phase token ledger |
| `gates.json` | Gate evaluation results |
| `artifacts.json` | Artifacts created during the run |
| `decisions.json` | Decisions recorded during the run |
| `proposal.json` | Change proposal (propose phase) |
| `apply-manifest.json` | Apply manifest (apply phase) |
| `verify-report.json` | Test results (verify phase) |
| `review.json` | Aggregated review (review phase) |

## Health Checks

Verify harness and adapter health:

```bash
opencontext verify
```

Relevant checks include:
- **Harness Phases**: 6/6 phases available
- **Harness Runner**: Runner instantiatable and run_id generated
- **Adapters**: Core adapters ready (local, python, aider)
- **Boundary Service**: Service accepts 6 adapter targets

## Migration from Legacy SDD Commands

The individual `sdd explore`, `sdd propose`, `sdd apply`, `sdd verify`, `sdd review`, `sdd archive`, and `sdd up-code` commands are **deprecated** in favor of the unified harness runner:

| Old command | New command |
|-------------|-------------|
| `sdd explore "query"` | `harness run --workflow explore-only --task "query"` |
| `sdd propose "query"` | `harness run --workflow sdd --task "query"` |
| `sdd apply --workflow sdd` | `harness run --workflow sdd --task "task"` |
| `sdd verify` | `harness run --workflow sdd --task "task"` |
| `sdd review` | `harness run --workflow sdd --task "task"` |
| `sdd archive` | `harness run --workflow explore-only --task "task"` |
| `sdd flow "query"` | `harness run --workflow sdd --task "query"` |

## Phase Dependencies (Orchestrator-Level)

The SDD orchestrator enforces dependency ordering at the skill/agent level:

- `explore`: no dependencies
- `propose`: depends on `explore`
- `apply`: depends on `propose`
- `verify`: depends on `apply`
- `review`: depends on all prior phases
- `archive`: depends on `verify`

## Technology Agnosticism

The harness workflow works identically across all technology stacks:

### Python/Django
```bash
opencontext harness run --workflow sdd --task "Create user registration endpoint"
```

### Node.js/Express
```bash
opencontext harness run --workflow sdd --task "Add JWT authentication middleware"
```

### React/TypeScript
```bash
opencontext harness run --workflow sdd --task "Implement login form with validation"
```

## See Also

- [Harness Runner Architecture](../concepts/architecture.md)
- [Custom Workflows](./custom-workflows.md)
- [CLI Reference](../getting-started/cli-installation.md)
- [Health Checks](../operations/health-checks.md)
