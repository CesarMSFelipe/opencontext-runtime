# OpenContext Architecture Risk Register
## Version 1.0 (Draft)
### Document ID
OC-RISK-001

# Purpose

This document defines the architectural risk register for OpenContext.

It identifies the major risks that could prevent OpenContext from becoming a reliable Engineering Operating System and defines mitigations, owners, early warning signals and acceptance criteria.

---

# Risk Categories

- Runtime complexity
- Workflow drift
- Token cost growth
- Context quality
- Safety and policy bypass
- Plugin ecosystem risk
- Provider dependency
- Memory pollution
- KG staleness
- UX complexity
- Benchmark weakness
- Enterprise adoption risk

---

# Risk 1 — Runtime Becomes Too Complex

## Description

The Runtime may accumulate workflow-specific logic and become difficult to reason about.

## Impact

High.

## Mitigation

- Runtime remains workflow-neutral.
- Workflows are declarative.
- Harnesses are reusable.
- Public contracts are enforced.

## Early Warning Signals

- SDD-specific conditionals inside Runtime Core.
- OC Flow-specific logic inside Session Runtime.
- New workflows requiring Runtime changes.

---

# Risk 2 — SDD and OC Flow Diverge

## Description

SDD and OC Flow may duplicate infrastructure or evolve into incompatible systems.

## Impact

High.

## Mitigation

- Shared Runtime.
- Shared Persona Registry.
- Shared Skill Registry.
- Shared Harness Registry.
- Shared artifact/receipt/event model.

## Early Warning Signals

- Duplicate mutation logic.
- Duplicate context retrieval logic.
- Separate policy handling.

---

# Risk 3 — Token Cost Increases

## Description

Richer context, memory and KG retrieval may increase prompt size instead of reducing it.

## Impact

High.

## Mitigation

- Context budgets.
- Semantic compression.
- KG-first retrieval.
- Memory budget.
- Token benchmarks.

## Early Warning Signals

- Average OC Flow task exceeds target budget.
- Context envelopes grow without improved success.
- Full files frequently loaded without receipts.

---

# Risk 4 — Memory Pollution

## Description

Memory may accumulate low-quality, stale or speculative records.

## Impact

High.

## Mitigation

- Memory Harness.
- Evidence requirements.
- Promotion policy.
- Conflict detection.
- Supersession.

## Early Warning Signals

- Memory records without evidence.
- Repeated stale commands.
- Contradictory memories not flagged.

---

# Risk 5 — KG Staleness

## Description

The Knowledge Graph may become outdated and mislead context retrieval.

## Impact

High.

## Mitigation

- Incremental indexing.
- KG freshness score.
- Post-run graph deltas.
- Stale graph warnings.

## Early Warning Signals

- Retrieved symbols do not exist.
- Tests are mislinked.
- Owner resolution outdated.

---

# Risk 6 — Policy Bypass

## Description

Interfaces, plugins or workflows may mutate files or execute commands without Runtime policy.

## Impact

Critical.

## Mitigation

- Runtime API boundary.
- Policy Engine for all operations.
- Plugin permissions.
- CI security tests.

## Early Warning Signals

- Direct file writes outside Mutation Harness.
- Commands executed outside Command Policy.
- Plugin code accessing filesystem directly.

---

# Risk 7 — Harness Over-Strictness

## Description

Harnesses may block useful work too aggressively and harm UX.

## Impact

Medium.

## Mitigation

- off/warn/strict modes.
- Profile-based defaults.
- Actionable errors.
- Benchmark harness pass rates.

## Early Warning Signals

- High false positive rate.
- Users disable harnesses globally.
- Frequent unnecessary escalations.

---

# Risk 8 — First-Run UX Fails

## Description

The system may become powerful but too hard to use.

## Impact

Critical.

## Mitigation

- Balanced profile.
- init/doctor/index/run path.
- First-run benchmark.
- Progressive disclosure.

## Early Warning Signals

- First task requires manual config.
- Doctor output unclear.
- Errors are not actionable.

---

# Risk 9 — Plugin Ecosystem Weakens Safety

## Description

Plugins may introduce unsafe behaviour, broken contracts or unbounded complexity.

## Impact

High.

## Mitigation

- Plugin manifest.
- Permission model.
- Compatibility checks.
- Plugin benchmarks.
- Trust levels.

## Early Warning Signals

- Plugins depend on Runtime internals.
- Plugins request broad permissions.
- Plugins lack benchmarks.

---

# Risk 10 — Provider Lock-In

## Description

The Runtime may become tied to one LLM provider.

## Impact

Medium.

## Mitigation

- Provider Gateway.
- Capability-based routing.
- Fallback.
- Contract-based structured outputs.

## Early Warning Signals

- Provider-specific logic in workflows.
- Tests only pass with one provider.
- Cost model unavailable for alternatives.

---

# Risk 11 — Benchmark Gaming

## Description

Benchmarks may become too narrow and fail to represent real engineering quality.

## Impact

High.

## Mitigation

- Diverse benchmark suites.
- Golden repositories.
- Regression tasks.
- Security benchmarks.
- Framework-specific benchmarks.

## Early Warning Signals

- Benchmarks pass while user success drops.
- Token usage improves but correctness worsens.
- Too few real repositories in suite.

---

# Risk 12 — Architecture Documentation Drift

## Description

Code may diverge from architecture documents.

## Impact

High.

## Mitigation

- PR checklist.
- ADR process.
- Contract validation.
- Docs updated in same PR.

## Early Warning Signals

- Features merged without architecture reference.
- Public schemas undocumented.
- ADRs missing for major decisions.

---

# Risk Register Maintenance

The risk register should be reviewed:

- before releases;
- after major incidents;
- after architecture changes;
- after benchmark regressions;
- during roadmap planning.

---

# Risk Status Values

```text
open
mitigated
accepted
transferred
closed
```

---

# Risk Record Template

```md
## Risk ID

### Description

### Impact

### Likelihood

### Mitigation

### Owner

### Early Warning Signals

### Review Date

### Status
```

---

# Definition of Done

Risk management is implemented when:

- risk register exists;
- risks have owners;
- release checklist references risks;
- major regressions update risk status;
- Studio can surface runtime risk indicators.

---

# Final Statement

OpenContext must manage architecture risk explicitly.

A system designed to reduce uncertainty must first understand its own risks.
