# OpenContext Global Definition of Done Checklist
## Version 1.0 (Draft)
### Document ID
OC-GLOBAL-DOD-001

# Purpose

This document defines the global Definition of Done for OpenContext.

It consolidates the completion criteria across all architecture documents into a single checklist.

---

# 1. Product-Level Definition of Done

OpenContext is product-complete when:

- first install works;
- first task succeeds;
- SDD works;
- OC Flow works;
- Runtime is workflow-neutral;
- context is budgeted;
- KG retrieval works;
- memory is governed;
- harnesses validate;
- policies enforce safety;
- artifacts and receipts persist evidence;
- Runtime Intelligence reports cost/confidence;
- benchmarks validate quality;
- Studio explains runs;
- plugins extend safely.

---

# 2. Runtime Checklist

- [ ] Runtime API exists.
- [ ] Sessions exist.
- [ ] Runs exist.
- [ ] WorkflowRunner exists.
- [ ] State transitions are validated.
- [ ] Events are emitted.
- [ ] Artifacts are persisted.
- [ ] Receipts are persisted.
- [ ] Checkpoints exist.
- [ ] Rollback works.
- [ ] Resume works.
- [ ] Consolidation works.
- [ ] Escalation works.

---

# 3. Workflow Checklist

## SDD

- [ ] Explore works.
- [ ] Propose works.
- [ ] Spec works.
- [ ] Design works.
- [ ] Tasks works.
- [ ] Apply works.
- [ ] Verify works.
- [ ] Review works.
- [ ] Archive works.

## OC Flow

- [ ] Init works.
- [ ] Gather context works.
- [ ] Plan works.
- [ ] Mutate works.
- [ ] Local inspection works.
- [ ] Diagnose works.
- [ ] Escalation works.
- [ ] Consolidation works.

---

# 4. Governance Checklist

- [ ] Policy Engine exists.
- [ ] Security Harness exists.
- [ ] File policies are enforced.
- [ ] Command policies are enforced.
- [ ] Provider redaction works.
- [ ] Plugin permissions work.
- [ ] Approvals are recorded.
- [ ] Denials are actionable.

---

# 5. Cognitive Runtime Checklist

- [ ] Knowledge Graph exists.
- [ ] KG indexing works.
- [ ] KG retrieval works.
- [ ] Memory exists.
- [ ] Memory promotion works.
- [ ] Memory conflict detection works.
- [ ] ContextEnvelope exists.
- [ ] Semantic compression works.
- [ ] Semantic GC works.

---

# 6. Agent System Checklist

- [ ] PersonaRegistry exists.
- [ ] SkillRegistry exists.
- [ ] HarnessRegistry exists.
- [ ] Built-in personas exist.
- [ ] Built-in skills exist.
- [ ] Built-in harnesses exist.
- [ ] Output contracts are validated.
- [ ] Tool permissions are enforced.

---

# 7. Runtime Intelligence Checklist

- [ ] Cost estimates exist.
- [ ] Actual cost reports exist.
- [ ] Confidence reports exist.
- [ ] Simulator exists.
- [ ] Profiler exists.
- [ ] Health report exists.
- [ ] Evolution candidates exist.
- [ ] Benchmarks gate promotion.

---

# 8. UX Checklist

- [ ] init works.
- [ ] doctor works.
- [ ] index works.
- [ ] run works.
- [ ] workflow explain works.
- [ ] profile explain works.
- [ ] config doctor works.
- [ ] useful summaries are returned.
- [ ] errors are actionable.
- [ ] artifact links are shown.

---

# 9. Platform Checklist

- [ ] Plugin SDK exists.
- [ ] Plugin manifest exists.
- [ ] Marketplace package format exists.
- [ ] Studio exists.
- [ ] MCP tools use Runtime API.
- [ ] CLI uses Runtime API.
- [ ] Public contracts are versioned.
- [ ] ADR process exists.

---

# 10. Benchmark Checklist

- [ ] First-run benchmark passes.
- [ ] SDD benchmark passes.
- [ ] OC Flow benchmark passes.
- [ ] Security benchmark passes.
- [ ] KG benchmark passes.
- [ ] Memory benchmark passes.
- [ ] Plugin benchmark passes.
- [ ] Provider fallback benchmark passes.

---

# 11. Release Checklist

- [ ] Public contracts frozen.
- [ ] Migration guide exists.
- [ ] Changelog exists.
- [ ] Release notes exist.
- [ ] Docs index updated.
- [ ] Architecture docs accepted.
- [ ] Security review completed.
- [ ] Full benchmark suite passes.

---

# 12. Final Statement

OpenContext is done when the architecture is not merely described, but enforced by Runtime contracts, tests, benchmarks and user-facing behaviour.
