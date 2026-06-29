# OpenContext Roadmap & Implementation Plan
## Version 1.0 (Draft)
### Document ID
OC-ROADMAP-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`
- `02-runtime-architecture.md`
- `03-sdd-workflow-architecture.md`
- `04-oc-flow-architecture.md`
- `05-persona-architecture.md`
- `06-skill-architecture.md`
- `07-harness-architecture.md`
- `08-knowledge-graph-architecture.md`
- `09-memory-architecture.md`
- `10-context-engineering-architecture.md`
- `11-runtime-intelligence-architecture.md`
- `12-plugin-extension-architecture.md`
- `13-configuration-ux-architecture.md`
- `14-observability-benchmark-architecture.md`
- `15-policy-security-architecture.md`

---

# 1. Purpose

This document defines the implementation roadmap for transforming the current `feat/agentic-engineering-runtime` branch into the target OpenContext Engineering Operating System.

The roadmap is designed to preserve compatibility while progressively introducing the new architecture.

It avoids a full rewrite.

It prioritizes:

- working software after every phase;
- compatibility with existing SDD flow;
- first-run usefulness;
- low token consumption;
- governed mutation;
- observable runtime behaviour;
- progressive migration to registries;
- measurable quality.

---

# 2. Implementation Philosophy

The implementation must follow three rules.

## Rule 1 — Do not break the current SDD flow

The current SDD pipeline is valuable and must continue to work.

Every migration step must keep `opencontext_run` usable.

## Rule 2 — Introduce platform primitives before new workflows

Do not add OC Flow as hardcoded logic.

First create:

- Session Runtime
- Workflow Registry
- Event Bus
- Artifact Store
- Receipt Store
- Policy Engine
- Harness Registry

Then add OC Flow.

## Rule 3 — Every phase must have a benchmark

No major subsystem should be considered done without a minimal benchmark or acceptance test.

---

# 3. Current Branch Baseline

The `feat/agentic-engineering-runtime` branch already contains important foundations:

- MCP server entrypoints
- `opencontext_run`
- HarnessRunner
- SDD phases
- `PhaseResultEnvelope`
- `ApplyEdit`
- delegation support
- personas
- skill resolver
- harness configuration
- memory provenance
- events
- gates
- apply/verify logic

The roadmap should preserve and harden these components rather than discarding them.

---

# 4. Target End State

At the end of this roadmap:

```bash
opencontext init --profile balanced
opencontext index
opencontext run "Fix failing test" --workflow auto
```

should:

1. detect project capabilities;
2. select OC Flow for localized bugfixes;
3. select SDD for formal/high-risk work;
4. retrieve context surgically;
5. apply changes through receipts;
6. verify locally;
7. diagnose bounded failures;
8. update KG and memory;
9. report cost/confidence;
10. show all artifacts and next action.

---

# 5. Implementation Phases

## Phase 0 — Baseline Stabilization

### Goal

Freeze current behaviour before refactoring.

### Tasks

- Add regression tests for `opencontext_run`.
- Add tests for existing SDD workflows.
- Add snapshot tests for output envelopes.
- Document current SDD phase order.
- Document current config fields.
- Document current artifact layout.
- Add first-run smoke test.

### Acceptance Criteria

- Current branch behaviour is reproducible.
- No migration starts without baseline tests.
- Existing users are protected.

---

## Phase 1 — Runtime Session Wrapper

### Goal

Introduce sessions without changing execution semantics.

### Tasks

- Add `RuntimeSession`.
- Add `RuntimeRun`.
- Add `SessionStore`.
- Wrap existing `HarnessRunner.run()` in session creation.
- Persist `session.json`.
- Persist `live-state.json`.
- Persist `config-snapshot.yaml`.

### Files

```text
opencontext_core/runtime/session.py
opencontext_core/runtime/session_store.py
opencontext_core/runtime/live_state.py
```

### Acceptance Criteria

- Every run belongs to a session.
- Legacy output still works.
- Session metadata is persisted.

---

## Phase 2 — Runtime Events

### Goal

Introduce a shared event model.

### Tasks

- Add `RuntimeEvent`.
- Add `EventBus`.
- Add JSONL event sink.
- Emit events from current phases.
- Emit events from policy/gates where available.
- Expose event path in `opencontext_run` output.

### Files

```text
opencontext_core/runtime/events.py
opencontext_core/runtime/event_bus.py
```

### Acceptance Criteria

- Every SDD phase emits start/completed events.
- Events are append-only.
- Studio/TUI can read event stream later.

---

## Phase 3 — Artifact Store

### Goal

Make durable outputs first-class.

### Tasks

- Add `ArtifactRef`.
- Add `ArtifactStore`.
- Register existing phase outputs as artifacts.
- Add checksum support.
- Add artifact manifest.
- Update summary output.

### Files

```text
opencontext_core/runtime/artifacts.py
```

### Acceptance Criteria

- Spec/design/tasks/apply/verify artifacts are addressable.
- No major output exists only in chat.
- Artifact paths returned by MCP.

---

## Phase 4 — Receipt Store

### Goal

Create audit trail for important actions.

### Tasks

- Add generic `Receipt`.
- Add `ReceiptStore`.
- Add workflow selection receipts.
- Add context retrieval receipts.
- Add apply receipts.
- Add policy decision receipts.
- Add inspection receipts.

### Files

```text
opencontext_core/runtime/receipts.py
```

### Acceptance Criteria

- Every mutation has a receipt.
- Every workflow selection has a receipt.
- Receipts are linked to events and artifacts.

---

## Phase 5 — Workflow Registry

### Goal

Move workflow definitions out of hardcoded runner logic.

### Tasks

- Add `WorkflowDefinition`.
- Add `WorkflowNodeDefinition`.
- Add `WorkflowEdge`.
- Add `WorkflowRegistry`.
- Register current SDD as built-in workflow.
- Preserve aliases: `full`, `standard`, `quick`.

### Files

```text
opencontext_core/workflow/definition.py
opencontext_core/workflow/registry.py
opencontext_core/workflow/builtins/sdd.yaml
```

### Acceptance Criteria

- Existing SDD runs from registry.
- Legacy workflow names still resolve.
- Runtime remains compatible.

---

## Phase 6 — Workflow Runner Adapter

### Goal

Make current HarnessRunner delegate to generic workflow runner.

### Tasks

- Add `WorkflowRunner`.
- Add `NodeResult`.
- Map SDD phases to nodes.
- Keep `HarnessRunner.run()` as compatibility adapter.
- Ensure phase results convert to `NodeResult`.

### Files

```text
opencontext_core/runtime/workflow_runner.py
opencontext_core/workflow/result.py
```

### Acceptance Criteria

- SDD can run through `WorkflowRunner`.
- Existing `HarnessRunResult` still returned.
- No user-facing break.

---

## Phase 7 — Harden SDD Propose/Executor

### Goal

Fix known SDD execution gaps.

### Tasks

- Ensure `propose` is registered as work-producing phase.
- Add prompt/executor contract for propose.
- Ensure delegation result propagates envelope metadata.
- Ensure missing executor does not masquerade as success.
- Add scaffold policy: `allow`, `warn`, `block`.

### Acceptance Criteria

- Propose can produce real artifact.
- Scaffold status is explicit.
- Strict mode blocks scaffold success.

---

## Phase 8 — SDD Phase Handoffs

### Goal

Make SDD phase boundaries explicit.

### Tasks

- Add `PhaseHandoff`.
- Persist handoffs between phases.
- Include summary, constraints, artifact refs.
- Avoid raw conversation dependence.

### Files

```text
opencontext_core/workflow/handoff.py
```

### Acceptance Criteria

- Each SDD phase receives explicit inputs.
- Resume can rehydrate prior artifacts.
- Handoffs visible in artifacts.

---

## Phase 9 — ApplyEdit as Primary Mutation Path

### Goal

Make surgical mutation the default.

### Tasks

- Treat `ApplyEdit` as primary mutation contract.
- Keep whole-file edit as fallback.
- Add checksums before/after.
- Generate unified patch.
- Add rollback checkpoint.

### Acceptance Criteria

- Apply produces patch.diff.
- Apply produces receipts.
- Whole-file rewrite requires reason.

---

## Phase 10 — Local Inspection v1

### Goal

Verify locally before spending more tokens.

### Tasks

- Add syntax checks.
- Add secret scan.
- Add lint/test command adapters.
- Add capability-aware skip behaviour.
- Add inspection report.

### Files

```text
opencontext_core/harness/inspection/
```

### Acceptance Criteria

- Local inspection runs after apply.
- Missing tools are reported clearly.
- Inspection report is persisted.

---

## Phase 11 — Policy Engine v1

### Goal

Centralize safety decisions.

### Tasks

- Add `PolicyEngine`.
- Add `PolicyDecision`.
- Enforce forbidden paths.
- Enforce command allow/deny.
- Redact provider calls.
- Add approval flow scaffold.

### Files

```text
opencontext_core/policy/engine.py
opencontext_core/policy/decisions.py
```

### Acceptance Criteria

- Mutations pass policy.
- Commands pass policy.
- Denials are actionable.
- Decisions create events/receipts.

---

## Phase 12 — Capability Registry

### Goal

Detect project capabilities.

### Tasks

- Add `CapabilityRegistry`.
- Detect git, test runners, linters, package managers.
- Detect language/framework.
- Add `opencontext doctor`.

### Files

```text
opencontext_core/capabilities/registry.py
opencontext_core/capabilities/probes.py
```

### Acceptance Criteria

- Doctor reports useful project state.
- Workflows adapt to missing tools.
- First-run UX improves.

---

## Phase 13 — Configuration v2

### Goal

Centralize configuration.

### Tasks

- Add `opencontext.yaml` schema.
- Add profiles.
- Add config resolver.
- Add config snapshot.
- Add `config doctor`.

### Files

```text
opencontext_core/config/schema.py
opencontext_core/config/profiles.py
opencontext_core/config/resolver.py
```

### Acceptance Criteria

- Balanced profile works by default.
- Unknown config keys warn.
- Every run stores config snapshot.

---

## Phase 14 — Persona Registry

### Goal

Move personas behind stable contracts.

### Tasks

- Add `PersonaDefinition`.
- Add `PersonaRegistry`.
- Add `PersonaResolver`.
- Register existing personas.
- Add `oc-diagnostician`.
- Add `oc-security-reviewer`.

### Acceptance Criteria

- SDD resolves personas via registry.
- OC Flow can reuse personas.
- Tool permissions are declared.

---

## Phase 15 — Skill Registry v2

### Goal

Make skills contract-driven.

### Tasks

- Add `SkillDefinition`.
- Add skill tiers.
- Add skill bundles.
- Add output contracts.
- Add skill validation.
- Migrate existing SKILL.md support.

### Acceptance Criteria

- Personas load skill bundles.
- Skills are versioned.
- Skills declare gates and outputs.

---

## Phase 16 — Harness Registry

### Goal

Extract implicit checks into reusable harnesses.

### Tasks

- Add `HarnessDefinition`.
- Add `HarnessRegistry`.
- Add `HarnessResult`.
- Add `GateResult`.
- Register context/planning/mutation/inspection harnesses.
- Map SDD nodes to harnesses.

### Acceptance Criteria

- Harnesses execute declaratively.
- Harness results are persisted.
- Harness modes configurable by profile.

---

## Phase 17 — OC Flow MVP

### Goal

Introduce OC Flow as separate workflow.

### Tasks

- Add `oc-flow.yaml`.
- Implement nodes:
  - init
  - gather_context
  - plan
  - mutate
  - local_inspection
  - consolidation
- Use shared Runtime.

### Acceptance Criteria

- `opencontext run --workflow oc-flow` works.
- OC Flow does not duplicate SDD code.
- OC Flow produces artifacts.

---

## Phase 18 — OC Flow Diagnosis

### Goal

Add bounded repair loop.

### Tasks

- Add diagnosis node.
- Add `DiagnosisAttempt`.
- Enforce exactly three hypotheses.
- Prevent repeated failed strategy.
- Add attempt budget.
- Add semantic failure compression.

### Acceptance Criteria

- Recoverable failures route to diagnose.
- Max attempts enforced.
- Escalation after exhaustion.

---

## Phase 19 — OC Flow Escalation

### Goal

Stop safely when non-convergent.

### Tasks

- Add escalation node.
- Add `EscalationReport`.
- Resolve owners where possible.
- Generate handoff.
- Stop token burn.

### Acceptance Criteria

- Exhausted diagnosis escalates.
- Handoff artifact exists.
- Session ends in governed state.

---

## Phase 20 — Context Engine v1

### Goal

Standardize context retrieval.

### Tasks

- Add `ContextEnvelope`.
- Add L1/L2/L3 layers.
- Add context budget.
- Add omission tracking.
- Integrate with SDD explore and OC Flow gather_context.

### Acceptance Criteria

- Context is budgeted.
- Context envelope persisted.
- Both workflows share context system.

---

## Phase 21 — Knowledge Graph v2

### Goal

Make KG code-native and queryable.

### Tasks

- Add KG schema v2.
- Add node/edge types.
- Add evidence refs.
- Add incremental graph delta.
- Add query planner.
- Add subgraph retrieval.

### Acceptance Criteria

- KG supports symbol/test/owner retrieval.
- Context Harness uses KG first.
- KG receipts/events exist.

---

## Phase 22 — Memory v2

### Goal

Make memory durable and governed.

### Tasks

- Add `MemoryRecord`.
- Add `MemoryCandidate`.
- Add memory promotion policy.
- Add conflict detection.
- Add supersession.
- Add project memory files.

### Acceptance Criteria

- Memory writes pass through Memory Harness.
- No chain-of-thought saved.
- Memory retrieval is budgeted.

---

## Phase 23 — Semantic Compression

### Goal

Reduce token waste.

### Tasks

- Add ContextCompressor.
- Add FailureCompressor.
- Add SemanticGC.
- Add compression receipts.
- Trigger after repeated failures.

### Acceptance Criteria

- Repeated failures are compressed.
- Context budget enforcement improves.
- Failed strategies preserved.

---

## Phase 24 — Runtime Intelligence v1

### Goal

Add cost/confidence/simulation.

### Tasks

- Add Cost Engine.
- Add Confidence Engine.
- Add Runtime Simulator.
- Add profiler scaffold.
- Add workflow comparison.

### Acceptance Criteria

- Workflow auto includes cost/confidence.
- Summaries show token savings.
- Low confidence changes behaviour.

---

## Phase 25 — Observability & Benchmarks

### Goal

Make quality measurable.

### Tasks

- Add benchmark task schema.
- Add first-run benchmark.
- Add OC Flow bugfix benchmark.
- Add SDD feature benchmark.
- Add health report.
- Add telemetry export.

### Acceptance Criteria

- Benchmarks can run locally.
- Runtime changes have measurable impact.
- Health command exists.

---

## Phase 26 — Plugin SDK v1

### Goal

Enable extensibility.

### Tasks

- Add PluginManifest.
- Add PluginRegistry.
- Add extension points for skills/personas/harnesses.
- Add permission validation.
- Add plugin health check.

### Acceptance Criteria

- Plugin can add a skill.
- Plugin can add a persona.
- Plugin cannot bypass runtime policy.

---

## Phase 27 — Studio MVP

### Goal

Visualize runtime execution.

### Tasks

- Add local Studio command.
- Read sessions/events/artifacts.
- Display workflow timeline.
- Display context/memory/receipts.
- Display cost/confidence.

### Acceptance Criteria

- `opencontext studio` opens local UI.
- User can inspect a run.
- No runtime dependency on Studio.

---

## Phase 28 — First-Run Polish

### Goal

Optimize onboarding.

### Tasks

- Improve `opencontext init`.
- Improve `opencontext doctor`.
- Improve `opencontext run` output.
- Add helpful missing-tool messages.
- Add default balanced config.
- Add example project guide.

### Acceptance Criteria

- New user can run first task successfully.
- No advanced config required.
- Output includes artifacts and next action.

---

## Phase 29 — Documentation Consolidation

### Goal

Publish architecture docs as official spec.

### Tasks

- Organize docs under `docs/architecture`.
- Add index.
- Add ADR template.
- Add contribution checklist.
- Add contract reference.
- Add migration notes.

### Acceptance Criteria

- Contributors can navigate docs.
- PRs reference architecture docs.
- ADR process exists.

---

## Phase 30 — Release Candidate

### Goal

Prepare first complete release.

### Tasks

- Run full benchmark suite.
- Run migration tests.
- Run plugin tests.
- Run security tests.
- Freeze public contracts.
- Generate release notes.

### Acceptance Criteria

- First-run benchmark passes.
- SDD benchmark passes.
- OC Flow benchmark passes.
- No critical policy bypass.
- Public contracts documented.

---

# 6. Release Strategy

## 0.x

Experimental runtime and SDD hardening.

## 0.5

Workflow Registry, sessions, events, artifacts.

## 0.7

OC Flow MVP.

## 0.8

KG/memory/context v2.

## 0.9

Runtime Intelligence and benchmarks.

## 1.0

Stable public contracts and plugin SDK.

---

# 7. Implementation Priorities

Highest priority:

1. Preserve current SDD.
2. Introduce sessions/events/artifacts/receipts.
3. Introduce workflow registry.
4. Harden SDD.
5. Add OC Flow.
6. Add context/KG/memory.
7. Add intelligence/benchmarks.
8. Add Studio/plugins.

---

# 8. Risks

## Risk: Over-refactor

Mitigation:

- wrapper first;
- adapters;
- compatibility tests.

## Risk: Config complexity

Mitigation:

- profiles;
- config doctor;
- good defaults.

## Risk: Token cost grows

Mitigation:

- context budgets;
- semantic compression;
- local-first inspection.

## Risk: Harnesses become too strict

Mitigation:

- off/warn/strict modes;
- profile-based defaults;
- actionable errors.

## Risk: Plugin API freezes too early

Mitigation:

- mark experimental until 1.0;
- version contracts;
- keep internal APIs private.

---

# 9. PR Checklist

Every PR must answer:

1. Which architecture document does this implement?
2. Which contract does it introduce or modify?
3. Which benchmark covers it?
4. Which policy/harness applies?
5. Does it preserve existing SDD?
6. Does it improve or preserve first-run UX?
7. Does it add events/receipts where needed?
8. Does it avoid unnecessary LLM usage?
9. Does it preserve backwards compatibility?
10. Does it update documentation?

---

# 10. Final Definition of Done

The roadmap is complete when:

- current SDD is stable and improved;
- OC Flow exists and works;
- sessions/events/artifacts/receipts exist;
- context is budgeted;
- KG retrieval works;
- memory is governed;
- compression reduces token waste;
- personas/skills/harnesses are registries;
- policy engine enforces safety;
- Runtime Intelligence estimates cost/confidence;
- benchmarks validate changes;
- Studio visualizes runs;
- plugins extend safely;
- first install leads to a useful first task.

---

# 11. Final Statement

This roadmap must be implemented incrementally.

OpenContext should never disappear into a rewrite.

Every phase should leave the product more reliable, more observable and more useful than before.
