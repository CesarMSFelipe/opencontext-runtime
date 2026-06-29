# OpenContext Memory Architecture
## Version 1.0 (Draft)
### Document ID
OC-MEMORY-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`
- `02-runtime-architecture.md`
- `08-knowledge-graph-architecture.md`

---

# 1. Purpose

This document defines the Memory Architecture for OpenContext.

Memory is the durable learning layer of OpenContext. It exists to prevent repeated engineering work, preserve validated project knowledge and improve future workflow execution.

Memory is not chat history.

Memory is not a dump of previous runs.

Memory is not the Knowledge Graph.

Memory stores reusable, evidence-backed knowledge that helps future engineering decisions.

---

# 2. Mission

OpenContext Memory should answer:

- What did we learn before?
- Which commands work in this repository?
- Which conventions must be preserved?
- Which failure patterns recur?
- Which decisions still apply?
- Which previous strategy should not be repeated?
- Which knowledge is stale or superseded?

Memory exists to improve future execution quality while reducing tokens.

---

# 3. Core Principles

1. Memory stores durable knowledge only.
2. Memory must be evidence-backed.
3. Memory must support expiry and supersession.
4. Memory must never store chain-of-thought.
5. Memory must never store noisy raw logs.
6. Memory writes must be governed by Memory Harness.
7. Memory retrieval must be budgeted.
8. Memory conflicts must be detectable.
9. Memory should reduce future context retrieval cost.
10. Memory should improve correctness, not merely recall.

---

# 4. Position in the Architecture

```text
Runtime
  -> Memory Harness
    -> Memory Provider
      -> Episodic Memory
      -> Semantic Memory
      -> Procedural Memory
      -> Project Memory
      -> Failure Pattern Memory
      -> Harness Experience Memory
```

Memory serves:

- Workflow Selector
- Context Harness
- Diagnosis Harness
- Planning Harness
- Escalation Harness
- Consolidation Harness
- Runtime Intelligence
- Studio

---

# 5. Memory Types

## 5.1 Episodic Memory

Records what happened in a specific session or run.

Example:

```text
Run ocf-123 used OC Flow, touched session_store.py, failed first attempt, passed after rehydrating artifacts before phase skip.
```

Episodic memory is useful for audit and experience analysis.

It should not automatically become semantic memory.

## 5.2 Semantic Memory

Stores durable facts about the project.

Example:

```text
Session resume requires artifact carry-over before phase skipping.
```

## 5.3 Procedural Memory

Stores how to do recurring work in this repository.

Example:

```text
Run unit tests with: PYTHONPATH=packages/opencontext_core pytest tests/unit.
```

## 5.4 Project Memory

Human-readable curated project knowledge.

Example files:

```text
.opencontext/memory/conventions.md
.opencontext/memory/decisions.md
.opencontext/memory/commands.md
```

## 5.5 Failure Pattern Memory

Stores repeated failures and validated fixes.

Example:

```text
Failure: SDD resume skipped completed phase but missing artifact was not rehydrated.
Fix: load ArtifactStore before completed phase skip.
```

## 5.6 Harness Experience Memory

Stores runtime/harness outcome patterns.

Example:

```text
OC Flow diagnosis succeeds more often on pytest failures when targeted test command is available.
```

---

# 6. Memory Record Model

```python
class MemoryRecord(BaseModel):
    schema_version: str = "opencontext.memory.v1"
    id: str
    kind: MemoryKind
    scope: Literal["project", "repo", "workspace", "team", "user"]
    content: str
    structured: dict[str, Any]
    tags: list[str]
    confidence: float
    status: Literal["active", "stale", "superseded", "rejected"]
    evidence_refs: list[EvidenceRef]
    source_session_id: str | None
    source_run_id: str | None
    created_at: str
    last_seen_at: str
    valid_from: str | None
    valid_to: str | None
    supersedes: list[str]
    contradicted_by: list[str]
```

---

# 7. Memory Evidence

Every durable memory must include evidence.

Evidence may come from:

- source file lines;
- test output;
- run artifact;
- user statement;
- policy decision;
- KG node;
- receipt;
- benchmark result.

No memory should be written without provenance.

---

# 8. Memory Write Lifecycle

```text
Candidate Extraction
↓
Classification
↓
Deduplication
↓
Evidence Check
↓
Conflict Check
↓
Confidence Assignment
↓
Promotion Decision
↓
Persistence
↓
KG Linking
```

Only the Memory Harness may promote memory candidates.

Personas and skills may propose memory candidates but cannot persist durable memory directly.

---

# 9. Memory Candidate

```python
class MemoryCandidate(BaseModel):
    kind: MemoryKind
    content: str
    structured: dict[str, Any]
    proposed_by: str
    evidence_refs: list[EvidenceRef]
    expected_reuse: str
    confidence: float
```

---

# 10. Promotion Policy

A candidate may become memory only if:

- it is reusable;
- it is evidence-backed;
- it is not already known;
- it is not transient;
- it does not contain sensitive data;
- it does not contain chain-of-thought;
- it improves future execution.

Promotion decisions must create receipts.

---

# 11. Memory Retrieval

Memory retrieval must be task-aware.

```python
class MemoryQuery(BaseModel):
    task: str
    workflow: str
    node: str
    tags: list[str]
    max_records: int
    max_tokens: int
    min_confidence: float
```

Retrieval order:

```text
exact tags
↓
procedural memory
↓
failure patterns
↓
semantic memory
↓
episodic memory only if needed
```

---

# 12. Memory Budget

Memory retrieval has token budgets.

Defaults:

| Workflow | Node | Budget |
|---|---|---:|
| OC Flow | gather_context | 500-1000 |
| OC Flow | diagnose | 1000-2000 |
| SDD | explore | 1000-3000 |
| SDD | design | 1000-2000 |
| SDD | archive | no prompt budget, local processing |

---

# 13. Conflict Detection

Memory conflicts must be explicit.

Example:

```text
Old memory: use pytest
New memory: this repo uses nox for tests
```

The system should:

1. create contradiction relationship;
2. mark lower-confidence memory stale if evidence supports;
3. record decision;
4. surface uncertainty if unresolved.

---

# 14. Supersession

When new durable knowledge replaces old knowledge:

```python
old.status = "superseded"
old.valid_to = now
new.supersedes = [old.id]
```

This is required for:

- commands;
- architecture decisions;
- owners;
- conventions;
- failure patterns.

---

# 15. Memory Compression

Memory must be compressed before prompt injection.

Compression must preserve:

- fact;
- scope;
- evidence;
- confidence;
- current validity;
- warning if stale.

Example compressed memory:

```text
Known repo command: run unit tests with `PYTHONPATH=packages/opencontext_core pytest tests/unit`.
Evidence: run ocf-123.
Confidence: 0.94.
```

---

# 16. Project Memory Files

Human-readable project memory files:

```text
.opencontext/memory/
  project-profile.md
  conventions.md
  decisions.md
  commands.md
  failure-patterns.md
  owners.md
  environment.md
  harness-learnings.md
```

These files are curated summaries, not the full database.

---

# 17. commands.md

Purpose:

Store validated commands.

Example:

```md
# Commands

## Python tests
`PYTHONPATH=packages/opencontext_core pytest tests/unit`

Evidence:
- run ocf-123
- inspection report ocf-123/inspection.json

Status: active
```

---

# 18. decisions.md

Purpose:

Store durable architecture decisions.

Example:

```md
# Decisions

## Runtime remains workflow-neutral

Status: active
Evidence:
- OC-ARCH-001
- OC-RUNTIME-001

Rationale:
Workflows are declarations; runtime executes generic graphs.
```

---

# 19. failure-patterns.md

Purpose:

Store repeated failure patterns and fixes.

Example:

```md
# Failure Patterns

## Artifact rehydration missing on resume

Symptoms:
- phase skipped
- required artifact not loaded
- downstream phase fails

Fix:
Load ArtifactStore before marking phase complete.

Status: active
```

---

# 20. Relationship with KG

Memory and KG are distinct.

Memory stores durable knowledge.

KG stores relationships.

Memory records may be linked into the KG.

Examples:

- MemoryRecord -> SUPPORTS -> Decision
- FailurePattern -> FAILED_WITH -> Run
- Procedure -> CONFIGURES -> Command

---

# 21. Relationship with Compression

Compression reduces memory cost.

The Memory Harness uses Compression to produce prompt-safe memory summaries.

Raw memory records should not be injected directly unless already compact.

---

# 22. Relationship with Runtime Intelligence

Runtime Intelligence uses memory to:

- estimate cost;
- improve workflow selection;
- identify repeated failures;
- propose harness improvements;
- benchmark runtime evolution.

Runtime Intelligence may propose memory updates but cannot persist them directly.

---

# 23. Privacy and Security

Memory must never store:

- credentials;
- secrets;
- private keys;
- tokens;
- raw user-sensitive data;
- chain-of-thought;
- raw confidential logs unless explicitly allowed.

Memory writes must pass Security Harness.

---

# 24. Memory Events

Required events:

- memory.candidate.created
- memory.candidate.rejected
- memory.record.created
- memory.record.updated
- memory.record.superseded
- memory.conflict.detected
- memory.retrieved
- memory.compressed

---

# 25. Memory Receipts

Every memory write creates a receipt.

```python
class MemoryReceipt(BaseModel):
    receipt_id: str
    memory_id: str
    action: Literal["create", "update", "supersede", "reject"]
    reason: str
    evidence_refs: list[EvidenceRef]
    created_at: str
```

---

# 26. Memory Provider Interface

```python
class MemoryProvider(Protocol):
    def search(self, query: MemoryQuery) -> list[MemoryRecord]: ...
    def get(self, memory_id: str) -> MemoryRecord: ...
    def write(self, record: MemoryRecord) -> MemoryReceipt: ...
    def supersede(self, old_id: str, new_id: str) -> MemoryReceipt: ...
    def detect_conflicts(self, candidate: MemoryCandidate) -> list[MemoryConflict]: ...
```

The architecture must support pluggable memory providers.

---

# 27. First-Run Behaviour

On first installation:

- memory starts empty;
- setup records project profile;
- commands discovered by doctor may become procedural memory;
- first run produces memory candidates;
- only high-confidence durable facts are promoted.

---

# 28. Configuration

```yaml
memory:
  enabled: true
  provider: local
  episodic: true
  semantic: true
  procedural: true
  project_memory: true
  failure_patterns: true
  harness_experience: true
  promotion_policy: evidence_based
  min_confidence: 0.75
  max_prompt_records: 8
  write_receipts: true
```

---

# 29. Migration from Current Branch

The current branch already includes memory-related provenance.

Migration should:

1. preserve existing memory store;
2. add MemoryRecord v1 schema;
3. add MemoryCandidate;
4. add Memory Harness;
5. add memory receipts;
6. add project memory files;
7. add conflict detection;
8. add supersession;
9. integrate memory retrieval with SDD explore;
10. integrate memory retrieval with OC Flow gather_context and diagnose.

---

# 30. Invariants

1. Memory is evidence-backed.
2. Memory is not chat history.
3. Memory does not store chain-of-thought.
4. Personas do not write durable memory directly.
5. Memory writes pass through Memory Harness.
6. Memory retrieval is budgeted.
7. Memory conflicts are explicit.
8. Memory supports supersession.
9. Project memory files are curated summaries.
10. Memory must reduce future uncertainty.

---

# 31. Definition of Done

Memory Architecture is implemented when:

- MemoryRecord schema exists.
- MemoryCandidate schema exists.
- Memory Harness exists.
- Memory writes create receipts.
- Project memory files are generated.
- Retrieval is budgeted.
- Conflict detection works.
- Supersession works.
- SDD uses memory.
- OC Flow uses memory.
- Consolidation promotes durable knowledge.
- Security prevents unsafe memory writes.

---

# 32. Final Statement

Memory is how OpenContext learns.

But OpenContext should not remember more.

It should remember better.
