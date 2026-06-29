# OpenContext PR-002 Artifacts, Receipts & Resume Implementation Specification
## Version 1.0 (Draft)
### Document ID
OC-PR-002-ARTIFACTS

# Purpose

This document specifies the second implementation pull request for OpenContext.

PR-002 introduces durable execution evidence through artifacts, receipts, manifests, checkpoints and resume support while remaining fully compatible with the Runtime Core introduced in PR-001.

---

# Scope

PR-002 adds:

- ArtifactStore
- ReceiptStore
- RunManifest
- CheckpointManager
- ResumeManager
- ApplyReceipt
- Patch metadata
- Rollback foundations

PR-002 does **not** introduce:

- Workflow Registry
- OC Flow
- Runtime Intelligence
- Plugin SDK
- Studio

---

# Architecture References

- 24-artifact-receipt-lifecycle.md
- 02-runtime-architecture.md
- 17-public-contracts-api-specification.md
- 49-pr-sequencing-plan.md

---

# Goals

1. Every important output becomes an Artifact.
2. Every important decision becomes a Receipt.
3. Every mutation creates a Checkpoint.
4. Every run owns a Manifest.
5. Resume restores execution state safely.
6. Rollback foundations exist.

---

# Proposed Files

```text
opencontext_core/runtime/
  artifact_store.py
  receipt_store.py
  manifest.py
  checkpoints.py
  resume.py
  rollback.py
```

---

# Session Layout

```text
.opencontext/sessions/<session_id>/
  session.json
  live-state.json
  events.jsonl

  runs/<run_id>/
    run.json
    manifest.json

    artifacts/
    receipts/
    checkpoints/
    patches/
```

---

# Artifact Types

Required built-ins:

- patch
- inspection-report
- summary
- context-envelope
- diagnosis-report
- benchmark-report

---

# Receipt Types

Required built-ins:

- mutation
- inspection
- policy
- provider
- memory-write
- kg-update
- consolidation

---

# Checkpoints

Before every mutation:

1. Snapshot files.
2. Calculate checksums.
3. Persist metadata.
4. Link checkpoint in manifest.

---

# Resume

Resume algorithm:

1. Load session.
2. Load run.
3. Validate manifest.
4. Validate artifact integrity.
5. Restore live state.
6. Continue from last completed node.

Resume must fail safely if evidence is inconsistent.

---

# Manifest

Every run owns:

```json
{
  "artifacts": [],
  "receipts": [],
  "checkpoints": [],
  "events": "events.jsonl"
}
```

---

# Tests

Required tests:

- artifact persisted
- receipt persisted
- manifest updated
- checkpoint created
- resume succeeds
- checksum mismatch detected
- rollback metadata created

---

# Acceptance Criteria

PR-002 is complete when:

- every mutation creates evidence;
- resume restores state;
- manifests remain valid;
- artifacts and receipts are queryable;
- Runtime compatibility is preserved.

---

# Rollback Strategy

Configuration flag:

```yaml
runtime:
  durable_artifacts: true
```

Disabling the feature returns to PR-001 behaviour without breaking execution.

---

# Final Statement

PR-002 transforms Runtime execution into durable engineering evidence.

After this PR, every important action is explainable, resumable and auditable.
