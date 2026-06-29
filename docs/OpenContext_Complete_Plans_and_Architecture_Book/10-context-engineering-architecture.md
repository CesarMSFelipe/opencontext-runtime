# OpenContext Context Engineering & Semantic Compression Architecture
## Version 1.0 (Draft)
### Document ID
OC-CONTEXT-001

## Purpose

This document defines how OpenContext retrieves, builds, compresses, validates and delivers context to workflows while minimizing token consumption.

Context Engineering is the primary mechanism that differentiates OpenContext from prompt-based systems.

---

# Mission

Deliver the minimum sufficient context required for a workflow node to succeed.

Correctness is maximized by reducing irrelevant information, not by increasing prompt size.

---

# Core Principles

1. Local evidence before LLM.
2. KG before repository traversal.
3. Memory before file loading.
4. Symbol before file.
5. Snippet before full file.
6. Context is budgeted.
7. Compression preserves engineering meaning.
8. Every retrieval produces receipts.
9. Every omission is explicit.
10. Context expires after use unless promoted.

---

# Context Layers

## L3 — Structural Context

Contains:

- repository topology
- package boundaries
- symbol signatures
- owners
- architecture decisions
- public contracts

Primary source:

Knowledge Graph.

## L2 — Task Contract

Contains:

- workflow contract
- acceptance criteria
- constraints
- verification strategy
- risk
- required artifacts

Immutable during execution.

## L1 — Ephemeral Working Context

Contains:

- focused files
- snippets
- current diagnostics
- stack traces
- changed symbols
- targeted tests

Purged after successful consolidation.

---

# Context Pipeline

```text
Intent
↓
Workflow Selection
↓
KG Query Planning
↓
Memory Retrieval
↓
Symbol Retrieval
↓
Snippet Selection
↓
Budget Estimation
↓
Semantic Compression
↓
Context Envelope
↓
Workflow Node
```

---

# Context Envelope

```python
class ContextEnvelope(BaseModel):
    schema_version: str = "opencontext.context.v1"
    workflow: str
    node: str
    task: str
    l3: dict
    l2: dict
    l1: dict
    token_estimate: int
    evidence_refs: list
    omissions: list
    confidence: float
```

---

# Retrieval Strategies

Supported strategies:

- symbol_first
- test_first
- owner_first
- failure_first
- architecture_first
- decision_first
- command_first

The Context Harness selects the strategy dynamically.

---

# Context Budget

Suggested defaults:

| Workflow | Budget |
|---|---:|
| OC Flow | 4k-6k |
| SDD Explore | 8k-15k |
| SDD Design | 6k-10k |
| Review | 3k-5k |

Budgets are configurable.

---

# Semantic Compression

Compression never removes engineering meaning.

Priority order:

Keep:

- acceptance criteria
- constraints
- signatures
- diagnostics
- evidence
- failed strategies

Compress:

- repeated logs
- duplicate snippets
- repeated discussions
- long stack traces
- repetitive plans

Discard:

- obsolete intermediate reasoning
- superseded attempts
- transient context
- duplicated tool output

---

# Garbage Collection

Compression is incremental.

Triggers:

- second failed diagnosis
- context budget exceeded
- workflow transition
- consolidation

Output:

```text
Attempt 1 failed because...
Attempt 2 failed because...
Do not retry strategy X.
Current verified hypothesis: Y.
```

---

# Retrieval Receipts

Every retrieval generates:

- query receipt
- budget receipt
- compression receipt
- omission receipt

---

# Context Profiles

Profiles:

- balanced
- low-cost
- performance
- enterprise
- research

Profiles adjust:

- retrieval depth
- compression aggressiveness
- memory limits
- file loading thresholds

---

# Configuration

```yaml
context:
  strategy: adaptive
  kg_first: true
  symbol_first: true
  full_file_threshold: 0.8
  semantic_gc: true
  receipts: true
  budgets:
    oc_flow: 6000
    sdd: 14000
```

---

# Migration

Current context loading should migrate incrementally:

1. Preserve existing retrieval.
2. Introduce ContextEnvelope.
3. Introduce Context Budget.
4. Add semantic compression.
5. Add omission tracking.
6. Integrate with Memory and KG.
7. Emit receipts.

---

# Invariants

- Every prompt uses ContextEnvelope.
- Context is budgeted.
- Compression preserves facts.
- KG precedes repository traversal.
- Memory precedes files.
- Receipts are mandatory.
- L1 is ephemeral.
- L2 is immutable.
- L3 is structural.

---

# Definition of Done

Implemented when:

- ContextEnvelope exists.
- Adaptive retrieval works.
- Semantic compression works.
- Budget enforcement works.
- Receipts are generated.
- SDD and OC Flow share the same Context Engine.
- Token usage is measurably reduced.

---

# Final Statement

Context Engineering is the intelligence amplifier of OpenContext.

The best context is not the largest one.

It is the smallest context that still guarantees the correct engineering decision.
