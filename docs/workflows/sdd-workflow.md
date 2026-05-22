# Specification-Driven Development (SDD) Workflow

The SDD workflow is OpenContext's 8-phase specification-driven development lifecycle. It moves from exploration through specification, design, implementation, and verification, with full traceability via artifact stores and DAG state tracking.

## Overview

SDD is designed to be **technology-agnostic** and **agent-composable**. Each phase can run independently or as part of the full flow. Artifacts persist across phases through configurable backends (engram, openspec, hybrid).

### Key Principles

1. **Specification-First**: Define intent, scope, and spec before implementation
2. **Traceable**: Every phase produces artifacts linked by DAG state
3. **Composable**: Each phase can be used independently or chained
4. **Auditable**: Full provenance via artifact stores and trace IDs

## The SDD Workflow Phases

The SDD workflow consists of eight phases:

```
Explore → Propose → Spec → Design → Tasks → Apply → Verify → Archive
```

### 1. Explore

**Purpose**: Investigate the codebase and think through ideas before committing to a change.

- Reads relevant source files, symbol definitions, and call graphs
- Identifies affected areas and potential approaches
- Produces a lightweight exploration summary

**CLI**:
```bash
opencontext sdd explore "How does authentication work?" --root . --max-tokens 8000
```

**Produces**: Exploration summary with code references and identified scope.

### 2. Propose

**Purpose**: Create a change proposal with intent, scope, and approach.

- Defines what will change and why
- Outlines the approach and expected impact
- Flags risks and dependencies

**CLI**:
```bash
opencontext sdd propose "Implement OAuth2 support" --root .
```

**Produces**: Change proposal document with scope, approach, and risk assessment.

### 3. Spec

**Purpose**: Write detailed specifications with requirements and scenarios.

- Translates proposal into concrete requirements
- Defines acceptance criteria and edge cases
- Covers functional and non-functional requirements

**CLI**:
```bash
opencontext sdd spec --root .
```

**Produces**: Delta spec document with requirements, scenarios, and acceptance criteria.

### 4. Design

**Purpose**: Create the technical design and architecture approach.

- Defines component boundaries, interfaces, and data flow
- Covers module placement, API contracts, and migration strategy
- Addresses cross-cutting concerns (security, performance, observability)

**CLI**:
```bash
opencontext sdd design --root .
```

**Produces**: Technical design document with architecture decisions, interface definitions, and trade-offs.

### 5. Tasks

**Purpose**: Break the change into implementation tasks.

- Decomposes spec and design into actionable work units
- Identifies file-level changes and test requirements
- Orders tasks by dependency

**CLI**:
```bash
opencontext sdd tasks --root .
```

**Produces**: Task list with file-level change descriptions and dependencies.

### 6. Apply

**Purpose**: Implement code changes from task definitions.

- Executes the planned tasks against the codebase
- Integrates with the workflow engine for guided multi-step execution
- Supports custom workflows via `--workflow` flag

**CLI**:
```bash
opencontext sdd apply --workflow sdd --root .
```

**Produces**: Applied changes with execution results and trace ID.

### 7. Verify

**Purpose**: Validate that the implementation matches specs, design, and tasks.

- Runs tests and compares results against acceptance criteria
- Checks that all requirements from the spec are addressed
- Reports coverage gaps or regressions

**CLI**:
```bash
opencontext sdd verify --root .
```

**Produces**: Verification report with pass/fail status per requirement.

### 8. Archive

**Purpose**: Archive completed change artifacts and sync delta specs.

- Persists all phase artifacts to the configured artifact store
- Updates baseline specs with delta changes
- Cleans up temporary state

**CLI**:
```bash
opencontext sdd archive --root .
```

**Produces**: Archived artifact set with trace ID for future reference.

## Complete SDD Flow

Run all eight phases in sequence:

```bash
opencontext sdd flow "Implement OAuth2 authentication" --root . --max-tokens 8000
```

This executes the full pipeline:
1. Explore → 2. Propose → 3. Spec → 4. Design → 5. Tasks → 6. Apply → 7. Verify → 8. Archive

## Phase Dependencies

The orchestrator enforces dependency ordering: each phase requires its predecessors to complete before it can run. The dependency graph is:

- `explore`: no dependencies
- `propose`: depends on `explore`
- `spec`: depends on `propose`
- `design`: depends on `propose`
- `tasks`: depends on `spec` + `design`
- `apply`: depends on `tasks`
- `verify`: depends on `apply`
- `archive`: depends on `verify`

## Artifact Stores

SDD supports multiple persistence backends configured via `opencontext.yaml`:

| Mode | Backend | Use Case |
|------|---------|----------|
| `none` | NoneStore | Stateless / single-session |
| `engram` | EngramStore | Topic-keyed memory persistence |
| `openspec` | OpenSpecStore | File-based OpenSpec format |
| `hybrid` | HybridStore | Both engram + openspec |

Configured under `sdd.artifact_store.mode` in `opencontext.yaml`.

## Per-Phase Model Assignment

Each SDD phase can use a different LLM model via `SDDProfile`. Configured in `opencontext.yaml`:

```yaml
sdd:
  profiles:
    default:
      explore: { provider: openrouter, model: openrouter/auto }
      propose: { provider: anthropic, model: claude-sonnet-4-20250514 }
      spec:     { provider: anthropic, model: claude-sonnet-4-20250514 }
      design:   { provider: anthropic, model: claude-sonnet-4-20250514 }
      tasks:    { provider: openrouter, model: openrouter/auto }
      apply:    { provider: openrouter, model: openrouter/auto }
      verify:   { provider: anthropic, model: claude-sonnet-4-20250514 }
      archive:  { provider: mock, model: mock-llm }
```

## SDD Profile Manager

The `SDDProfileManager` manages named profiles for different scenarios:

```bash
# List available profiles
opencontext sdd profile list

# Set active profile
opencontext sdd profile set my-profile
```

## Technology Agnosticism

The SDD workflow works identically across all technology stacks:

### Python/Django
```bash
opencontext sdd flow "Create user registration endpoint"
```

### Node.js/Express
```bash
opencontext sdd flow "Add JWT authentication middleware"
```

### React/TypeScript
```bash
opencontext sdd flow "Implement login form with validation"
```

## See Also

- [SDD Orchestrator Architecture](../concepts/architecture.md)
- [Custom Workflows](./custom-workflows.md)
- [Provider Policies](../configuration/provider-policy.md)
