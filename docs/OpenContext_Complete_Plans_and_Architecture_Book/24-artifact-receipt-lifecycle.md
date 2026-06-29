# OpenContext Artifact, Receipt & Lifecycle Architecture
## Version 1.0 (Draft)
### Document ID
OC-ARTIFACTS-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`
- `02-runtime-architecture.md`
- `07-harness-architecture.md`
- `15-policy-security-architecture.md`

---

# 1. Purpose

This document defines the architecture for artifacts, receipts, manifests, patches, checkpoints, rollback and execution lifecycle records in OpenContext.

Artifacts and receipts are the durable evidence layer of OpenContext.

They make every execution auditable, resumable, reviewable and explainable.

---

# 2. Core Principle

No important runtime output should exist only in chat.

Every meaningful output must be persisted as an artifact.

Every meaningful decision or action must be represented by a receipt.

Artifacts answer:

```text
What was produced?
```

Receipts answer:

```text
Why and how was it produced?
```

---

# 3. Artifact vs Receipt

## Artifact

An artifact is durable output.

Examples:

- specification
- design
- task contract
- patch
- inspection report
- diagnosis report
- escalation report
- memory delta
- graph delta
- run summary

## Receipt

A receipt is proof of a decision or action.

Examples:

- workflow selection receipt
- context retrieval receipt
- mutation receipt
- policy receipt
- inspection receipt
- memory write receipt
- KG update receipt

---

# 4. Artifact Model

```python
class ArtifactRef(BaseModel):
    schema_version: str = "opencontext.artifact.v1"
    artifact_id: str
    session_id: str
    run_id: str
    workflow_id: str | None
    node_id: str | None
    kind: str
    path: str
    media_type: str
    produced_by: str
    checksum: str | None
    created_at: str
    metadata: dict[str, Any]
```

---

# 5. Receipt Model

```python
class Receipt(BaseModel):
    schema_version: str = "opencontext.receipt.v1"
    receipt_id: str
    session_id: str
    run_id: str | None
    workflow_id: str | None
    node_id: str | None
    kind: str
    action: str
    reason: str
    evidence_refs: list[str]
    artifact_refs: list[str]
    cost: dict[str, Any]
    policy_decision_id: str | None
    created_at: str
    metadata: dict[str, Any]
```

---

# 6. Artifact Store

The Artifact Store owns artifact registration and lookup.

```python
class ArtifactStore:
    def write(self, artifact: ArtifactWriteRequest) -> ArtifactRef: ...
    def get(self, artifact_id: str) -> ArtifactRef: ...
    def list_for_run(self, run_id: str) -> list[ArtifactRef]: ...
    def verify_checksum(self, artifact_id: str) -> bool: ...
```

---

# 7. Receipt Store

The Receipt Store owns receipt registration and lookup.

```python
class ReceiptStore:
    def write(self, receipt: Receipt) -> ReceiptRef: ...
    def get(self, receipt_id: str) -> Receipt: ...
    def list_for_run(self, run_id: str) -> list[Receipt]: ...
```

---

# 8. Session Layout

```text
.opencontext/sessions/<session_id>/
  session.json
  live-state.json
  events.jsonl
  config-snapshot.yaml

  runs/<run_id>/
    run.json
    workflow.json
    manifest.json
    artifacts/
    receipts/
    checkpoints/
    patches/
    logs/
    summaries/
```

---

# 9. Run Manifest

Each run has a manifest.

```python
class RunManifest(BaseModel):
    schema_version: str = "opencontext.run_manifest.v1"
    session_id: str
    run_id: str
    workflow_id: str
    status: str
    artifacts: list[ArtifactRef]
    receipts: list[ReceiptRef]
    checkpoints: list[CheckpointRef]
    events_path: str
    summary_path: str | None
    created_at: str
    updated_at: str
```

The manifest is the index for run evidence.

---

# 10. Patches

Every code mutation should produce a patch artifact.

```text
patches/
  patch-001.diff
  patch-002.diff
```

Patch metadata should include:

- changed files
- added lines
- removed lines
- mutation receipts
- checkpoint id
- verification status

---

# 11. Apply Receipt

```python
class ApplyReceipt(BaseModel):
    schema_version: str = "opencontext.apply_receipt.v1"
    receipt_id: str
    path: str
    operation: str
    changed: bool
    checksum_before: str | None
    checksum_after: str | None
    diff_path: str | None
    reason: str
    requirement_refs: list[str]
    policy_decision_id: str | None
```

Every mutation must have an ApplyReceipt.

---

# 12. Checkpoints

Before mutation, the runtime creates a checkpoint.

```python
class Checkpoint(BaseModel):
    schema_version: str = "opencontext.checkpoint.v1"
    checkpoint_id: str
    session_id: str
    run_id: str
    files: list[str]
    checksums: dict[str, str]
    snapshot_paths: dict[str, str]
    created_at: str
```

---

# 13. Rollback

Rollback restores checkpointed files.

Rollback produces:

- rollback event
- rollback receipt
- rollback report artifact

Rollback is required when:

- mutation fails partially;
- inspection fails in strict mode;
- policy violation is detected after mutation;
- user rejects pending change.

---

# 14. Artifact Lifecycle

```text
created
↓
validated
↓
referenced
↓
archived
↓
superseded or retained
```

Artifacts are never silently deleted.

Ephemeral artifacts may be purged only under explicit retention policy.

---

# 15. Receipt Lifecycle

Receipts are immutable.

A later receipt may supersede or correct a decision, but the original receipt remains.

---

# 16. Artifact Kinds

Required artifact kinds:

- context-envelope
- task-contract
- proposal
- spec
- design
- tasks
- mutation
- patch
- inspection-report
- diagnosis-attempt
- review-report
- escalation-report
- memory-delta
- graph-delta
- cost-report
- confidence-report
- summary

---

# 17. Receipt Kinds

Required receipt kinds:

- workflow-selection
- context-retrieval
- policy-decision
- provider-call
- mutation
- inspection
- diagnosis
- escalation
- memory-write
- kg-update
- consolidation
- benchmark

---

# 18. Checksums

Checksums are required for:

- mutated files before/after;
- patch files;
- artifact files;
- checkpoint snapshots;
- run manifests.

Checksums support resume, rollback and audit.

---

# 19. Resume

Resume must reload:

- run manifest;
- artifact refs;
- receipts;
- checkpoints;
- live state;
- workflow state.

If required artifacts are missing, resume fails safely.

---

# 20. Retention

Default retention:

```yaml
artifacts:
  retain:
    summaries: always
    receipts: always
    patches: always
    checkpoints: until_archive
    logs: 30d
    ephemeral_context: until_success
```

---

# 21. Events

Required events:

- artifact.created
- artifact.validated
- artifact.superseded
- receipt.created
- checkpoint.created
- rollback.started
- rollback.completed
- manifest.updated

---

# 22. Studio Integration

Studio should visualize:

- run manifest
- artifacts
- receipts
- patch history
- checkpoints
- rollback status
- evidence links

---

# 23. Migration from Current Branch

Migration steps:

1. Preserve current artifact output.
2. Add ArtifactRef.
3. Add RunManifest.
4. Add Receipt.
5. Add ApplyReceipt.
6. Add patch artifacts.
7. Add checkpoint artifacts.
8. Add resume validation.
9. Update MCP output to include artifact links.
10. Update Studio later.

---

# 24. Invariants

1. Important outputs are artifacts.
2. Important decisions are receipts.
3. Receipts are immutable.
4. Mutations require checkpoints.
5. Mutations require ApplyReceipts.
6. Patches are persisted.
7. Checksums are recorded.
8. Resume validates artifacts.
9. Rollback produces receipts.
10. Chat is not the artifact store.

---

# 25. Definition of Done

Implemented when:

- ArtifactStore exists.
- ReceiptStore exists.
- RunManifest exists.
- ApplyReceipt exists.
- Checkpoints exist.
- Rollback works.
- Patches are persisted.
- MCP returns artifact links.
- Resume validates required artifacts.
- Studio can render artifact/receipt timeline.

---

# 26. Final Statement

Artifacts and receipts are the evidence layer of OpenContext.

They turn agentic execution into auditable engineering work.
