# OpenContext Implementation Backlog & Epic Map
## Version 1.0 (Draft)
### Document ID
OC-EPICS-001

# Purpose

This document converts the OpenContext architecture book into an actionable implementation backlog.

It groups the roadmap into epics, capabilities, deliverables and acceptance criteria so the project can move from architecture to execution.

---

# Backlog Principles

1. Every epic maps to architecture documents.
2. Every epic has acceptance criteria.
3. Every epic preserves current SDD compatibility unless explicitly marked breaking.
4. Every epic improves first-run quality or platform maturity.
5. Every epic has tests or benchmarks.
6. Every epic produces user-visible value.

---

# Epic 1 — Runtime Foundation

## Goal

Create the stable execution foundation.

## Deliverables

- Runtime API
- RuntimeSession
- RuntimeRun
- SessionStore
- WorkflowRunner
- StateMachine
- EventBus
- LiveState

## Acceptance Criteria

- Every execution has a session.
- Events are persisted.
- Existing `opencontext_run` still works.
- Runtime remains workflow-neutral.

---

# Epic 2 — Artifacts, Receipts & Resume

## Goal

Make execution auditable and resumable.

## Deliverables

- ArtifactStore
- ReceiptStore
- RunManifest
- Checkpoints
- Rollback
- Resume validation

## Acceptance Criteria

- Mutations create receipts.
- Patches are persisted.
- Resume rehydrates artifacts.
- Rollback works for failed mutation.

---

# Epic 3 — Workflow Registry & SDD Hardening

## Goal

Preserve and improve current SDD.

## Deliverables

- WorkflowDefinition
- WorkflowRegistry
- SDD workflow definition
- Phase handoffs
- Propose executor fix
- Scaffold policy

## Acceptance Criteria

- SDD runs from registry.
- Existing aliases remain.
- Phase artifacts are explicit.
- Scaffolds cannot masquerade as success.

---

# Epic 4 — OC Flow

## Goal

Add operational agentic workflow.

## Deliverables

- OC Flow workflow definition
- Context gathering
- Plan-lite
- Surgical mutation
- Local inspection
- Diagnosis loop
- Escalation
- Consolidation

## Acceptance Criteria

- OC Flow completes bugfix benchmark.
- Diagnosis is bounded.
- Escalation produces handoff.
- OC Flow shares runtime infrastructure.

---

# Epic 5 — Registries

## Goal

Make personas, skills and harnesses declarative.

## Deliverables

- PersonaRegistry
- SkillRegistry
- HarnessRegistry
- Built-in definitions
- Output contracts
- Tool permissions

## Acceptance Criteria

- SDD and OC Flow resolve through registries.
- Skills expose contracts.
- Harnesses emit results.
- Tool permissions are enforced.

---

# Epic 6 — Policy & Security

## Goal

Runtime-enforced safety.

## Deliverables

- PolicyEngine
- PolicyDecision
- File policy
- Command policy
- Provider redaction
- Approval flow
- Security Harness

## Acceptance Criteria

- Unsafe writes are blocked.
- Commands are governed.
- Secrets are redacted.
- Approvals are receipted.

---

# Epic 7 — Cognitive Runtime

## Goal

Reduce token use and improve context quality.

## Deliverables

- Knowledge Graph v2
- Memory v2
- ContextEnvelope
- Semantic Compression
- Semantic GC
- KG/Memory receipts

## Acceptance Criteria

- Context retrieval is KG-first.
- Memory is evidence-backed.
- Compression reduces prompt size.
- OC Flow and SDD share Context Engine.

---

# Epic 8 — Runtime Intelligence

## Goal

Make execution measurable and self-improving.

## Deliverables

- Cost Engine
- Confidence Engine
- Runtime Simulator
- Profiler
- Runtime Health
- EvolutionCandidate

## Acceptance Criteria

- Workflow selection has cost/confidence.
- Simulation works.
- Health report exists.
- Evolution proposals require benchmarks.

---

# Epic 9 — Interfaces

## Goal

Expose the runtime consistently.

## Deliverables

- Improved MCP tools
- CLI commands
- Doctor
- Config doctor
- Workflow explain
- Profile explain
- Session status/resume

## Acceptance Criteria

- MCP and CLI call Runtime API.
- Outputs include artifacts/receipts.
- Errors are actionable.
- CI mode works.

---

# Epic 10 — Studio

## Goal

Visualize runtime execution.

## Deliverables

- Local Studio
- Session dashboard
- Workflow timeline
- Artifact/receipt viewer
- Context/KG/memory views
- Cost/confidence views
- Benchmark view

## Acceptance Criteria

- `opencontext studio` opens local UI.
- Studio consumes public contracts.
- Headless runtime still works.

---

# Epic 11 — Plugin SDK & Marketplace

## Goal

Make OpenContext extensible.

## Deliverables

- PluginManifest
- PluginRegistry
- SDK scaffolding
- Compatibility checks
- Marketplace package format
- Permission validation

## Acceptance Criteria

- Plugin can add skill/persona/harness.
- Plugin permissions are enforced.
- Marketplace install creates receipts.
- Compatibility is checked.

---

# Epic 12 — Evaluation & Release

## Goal

Ship safely.

## Deliverables

- Benchmark runner
- First-run suite
- SDD suite
- OC Flow suite
- Security suite
- Release checklist
- Migration tools
- Version command

## Acceptance Criteria

- Release gates pass.
- Migration is documented.
- Public contracts are versioned.
- First-run benchmark passes.

---

# Suggested Implementation Order

```text
1. Runtime Foundation
2. Artifacts & Receipts
3. Workflow Registry + SDD Hardening
4. Policy & Security
5. OC Flow
6. Registries
7. Cognitive Runtime
8. Runtime Intelligence
9. Interfaces
10. Studio
11. Plugin SDK
12. Evaluation & Release
```

---

# Final Statement

This backlog turns the architecture book into execution.

OpenContext should move forward through small, benchmarked, compatibility-preserving epics.
