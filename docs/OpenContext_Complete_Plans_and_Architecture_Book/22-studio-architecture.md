# OpenContext Studio Architecture
## Version 1.0 (Draft)
### Document ID
OC-STUDIO-001

# Purpose

This document defines the architecture for OpenContext Studio, the visual control plane for inspecting, understanding and operating OpenContext sessions.

Studio is not required for headless operation.

Studio visualizes the same runtime artifacts, events, receipts and contracts used by CLI, MCP and TUI.

# Mission

OpenContext Studio exists to answer:

- What is the runtime doing?
- Why did it choose this workflow?
- What context was used?
- What memory was retrieved?
- What changed?
- Which gates passed or failed?
- What did it cost?
- What is the confidence level?
- What should happen next?

# Core Principles

1. Studio observes; Runtime executes.
2. Studio reads public contracts only.
3. Studio must not depend on private runtime internals.
4. Every visualization must be backed by artifacts or events.
5. Studio should make hidden runtime state understandable.
6. Studio should support debugging, auditing and learning.
7. Studio must work locally first.
8. Studio must not be required in CI/headless mode.

# Position in Architecture

```text
Runtime
  -> Events
  -> Artifacts
  -> Receipts
  -> Live State
  -> Studio
```

Studio consumes:

- session.json
- live-state.json
- events.jsonl
- artifacts
- receipts
- traces
- metrics
- benchmark reports
- KG snapshots
- memory records

# Views

## Session Dashboard

Shows:

- task
- workflow
- profile
- status
- current node
- elapsed time
- cost
- confidence
- next action

## Workflow Timeline

Shows:

- nodes/phases
- completed status
- current node
- failed gates
- retries
- escalation

## Context View

Shows:

- ContextEnvelope
- L1/L2/L3 layers
- evidence references
- omissions
- token budget
- compression receipts

## Knowledge Graph View

Shows:

- relevant subgraph
- files
- symbols
- tests
- owners
- dependencies
- decisions
- failure patterns

## Memory View

Shows:

- retrieved memory
- memory candidates
- promoted records
- rejected records
- superseded records
- conflict warnings

## Patch & Receipts View

Shows:

- changed files
- diff
- ApplyEdit operations
- checksums
- rollback checkpoint
- mutation receipts

## Harness View

Shows:

- harnesses executed
- gate results
- warnings
- failures
- receipts
- metrics

## Runtime Intelligence View

Shows:

- cost estimates
- actual cost
- confidence report
- workflow comparison
- profiler breakdown
- token savings

## Benchmark View

Shows:

- benchmark history
- first-run results
- workflow regressions
- skill/harness performance
- runtime health trend

## Policy View

Shows:

- policy decisions
- approvals
- denials
- blocked operations
- security findings
- plugin permissions

# Local Deployment

Initial Studio runs locally:

```bash
opencontext studio
```

It serves a local UI and reads `.opencontext/` data.

No cloud service is required.

# Data Sources

Studio must consume stable contracts:

- RuntimeSession
- RuntimeRun
- RuntimeEvent
- ArtifactRef
- Receipt
- ContextEnvelope
- MemoryRecord
- KgSubgraph
- HarnessResult
- CostReport
- ConfidenceReport
- BenchmarkResult

# Permissions

Studio must respect Runtime Policy.

Studio may request approvals, but Runtime records and enforces them.

Studio cannot mutate files directly.

# UX Requirements

Studio should make runtime state understandable to both:

- advanced contributors;
- first-time users.

Default Studio should show a simple dashboard.

Advanced panels reveal deeper details progressively.

# Plugin Panels

Plugins may contribute Studio panels through Plugin SDK.

Examples:

- Drupal architecture panel
- Security review panel
- Benchmark suite panel
- Provider cost panel

Plugin panels consume public contracts only.

# Error UX

Studio should convert runtime errors into actionable explanations.

Example:

```text
Inspection failed because PHPUnit was not found.
Suggested action: configure inspection.tests.command.
```

# Invariants

1. Studio does not execute workflows.
2. Studio does not bypass Runtime API.
3. Studio uses public contracts.
4. Studio visualizations are evidence-backed.
5. Studio works locally.
6. Studio is optional.
7. Studio can render historical sessions.
8. Studio supports plugin panels safely.

# Definition of Done

Studio Architecture is implemented when:

- `opencontext studio` works locally.
- Session dashboard exists.
- Workflow timeline exists.
- Artifact and receipt views exist.
- Context and KG views exist.
- Cost/confidence views exist.
- Policy view exists.
- Benchmark view exists.
- Studio reads public contracts only.
- Headless runtime works without Studio.

# Final Statement

Studio is how OpenContext becomes understandable.

A powerful runtime without a visual control plane eventually becomes another black box.
