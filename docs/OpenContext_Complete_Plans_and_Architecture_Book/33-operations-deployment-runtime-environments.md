# OpenContext Operations, Deployment & Runtime Environments Blueprint
## Version 1.0 (Draft)
### Document ID
OC-OPERATIONS-001

# Purpose

This document defines how OpenContext should run across local, CI, remote, enterprise and hybrid environments.

It complements the Runtime, Enterprise and Release blueprints by defining the operational model for deploying, operating, monitoring and scaling OpenContext.

---

# Mission

OpenContext must work well in:

- local developer machines
- CI pipelines
- self-hosted enterprise environments
- managed cloud environments
- hybrid environments
- remote execution workers
- air-gapped environments

The same Runtime contracts should apply everywhere.

---

# Environment Types

## Local Runtime

Default mode.

Used by individual developers.

Characteristics:

- local filesystem
- local KG
- local memory
- local artifacts
- local Studio
- optional provider access

## CI Runtime

Non-interactive mode.

Characteristics:

- no approval prompts
- machine-readable output
- strict policies
- artifact export
- benchmark execution

## Remote Runtime

Runtime runs on managed or self-hosted infrastructure.

Characteristics:

- remote workers
- artifact sync
- secure provider routing
- centralized observability
- queue-based execution

## Hybrid Runtime

Local interface with remote execution.

Characteristics:

- local CLI/MCP
- remote workers
- local approval
- remote artifacts mirrored locally

## Air-Gapped Runtime

No external network.

Characteristics:

- local providers only
- local memory
- local KG
- no telemetry export
- strict plugin policy

---

# Runtime Deployment Modes

```yaml
deployment:
  mode: local # local|ci|remote|hybrid|air_gapped
```

---

# Operational Components

```text
Runtime API
Session Store
Artifact Store
Receipt Store
Event Bus
KG Store
Memory Store
Provider Gateway
Policy Engine
Studio
Worker Pool
Queue
Telemetry Exporter
```

---

# Worker Architecture

Remote and enterprise deployments may use workers.

Worker responsibilities:

- execute workflow nodes
- run local inspection
- run benchmarks
- update artifacts
- emit events
- obey policies

Workers must not own orchestration.

The Runtime Scheduler owns orchestration.

---

# Queue Model

Queue item:

```python
class RuntimeJob(BaseModel):
    job_id: str
    session_id: str
    run_id: str
    workflow_id: str
    node_id: str
    priority: str
    required_capabilities: list[str]
    policy_context: dict
```

---

# Storage

Storage may be:

- local filesystem
- SQLite
- object storage
- Postgres
- graph DB
- enterprise storage provider

Storage providers must implement stable contracts.

---

# Telemetry

Operational telemetry includes:

- runtime health
- worker health
- queue depth
- job duration
- provider latency
- token cost
- failure rate
- escalation rate
- policy denials

---

# Secrets

Secrets must be managed through provider-specific secret stores.

OpenContext must not store provider API keys in artifacts, memory, KG or receipts.

---

# Scaling

Scaling dimensions:

- worker count
- concurrent sessions
- KG indexing jobs
- benchmark jobs
- provider routing
- artifact storage
- Studio viewers

---

# CI Integration

CI mode should support:

```bash
opencontext run "Review this PR" --workflow review --ci
opencontext benchmark run first-run --ci
opencontext health --ci
```

CI output must include:

- exit code
- JSON report
- artifact paths
- policy failures
- benchmark results

---

# Backup & Restore

Backup targets:

- sessions
- artifacts
- receipts
- KG
- memory
- configuration
- plugin registry

Restore should validate schema compatibility.

---

# Disaster Recovery

Enterprise deployments should define:

- RPO
- RTO
- artifact retention
- session retention
- KG rebuild procedure
- memory restore procedure

---

# Operational Policies

Operations must respect:

- tenant isolation
- workspace isolation
- provider boundaries
- plugin permissions
- audit retention
- network policies

---

# Studio Operations

Studio can operate in:

- local mode
- read-only mode
- enterprise mode
- shared session mode

Studio must never bypass Runtime API.

---

# Configuration

```yaml
operations:
  deployment: local

  workers:
    enabled: false
    max_concurrency: 2

  storage:
    provider: filesystem

  telemetry:
    local_events: true
    otlp_export: false

  retention:
    sessions: 90d
    artifacts: 180d
    receipts: forever
```

---

# Events

Required events:

- operations.worker.started
- operations.worker.stopped
- operations.job.queued
- operations.job.started
- operations.job.completed
- operations.job.failed
- operations.backup.created
- operations.restore.completed

---

# Invariants

1. Deployment mode does not change Runtime contracts.
2. Workers do not own orchestration.
3. Remote execution obeys the same policies as local execution.
4. Artifacts and receipts remain durable.
5. Secrets are never stored in runtime artifacts.
6. CI mode is non-interactive by default.
7. Air-gapped mode never performs network calls.
8. Studio is optional.

---

# Definition of Done

Implemented when:

- local mode works;
- CI mode works;
- remote worker contract exists;
- storage providers are abstracted;
- telemetry is emitted;
- backup/restore is documented;
- air-gapped profile works;
- operational health is visible.

---

# Final Statement

OpenContext must be operationally boring.

The workflows may be intelligent, but the deployment model must be predictable, secure and observable.
