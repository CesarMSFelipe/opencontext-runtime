# OpenContext Reference Architecture (Executive Summary)
## Version 1.0 (Draft)
### Document ID
OC-REFERENCE-001

# Purpose

This document is the executive summary of the complete OpenContext architecture.

It is intended for architects, maintainers and enterprise adopters who need a concise reference without reading the entire architecture book.

---

# Architectural Pillars

OpenContext is built around five permanent pillars:

1. Runtime
2. Workflows
3. Cognitive Layer
4. Governance
5. Platform

These pillars evolve independently but communicate only through stable public contracts.

---

# Runtime

The Runtime owns:

- sessions
- runs
- workflow execution
- events
- artifacts
- receipts
- checkpoints
- rollback
- policy enforcement

The Runtime is workflow-neutral.

---

# Workflows

Two first-class workflows ship with OpenContext:

- SDD
- OC Flow

Additional workflows are installed through the Workflow Registry.

---

# Cognitive Layer

The cognitive layer combines:

- Knowledge Graph
- Memory
- Context Engineering
- Semantic Compression
- Runtime Intelligence

Its goal is to maximize engineering quality while minimizing token usage.

---

# Governance

Governance is enforced through:

- Policies
- Harnesses
- Capability Registry
- ADRs
- Benchmarks
- Public Contracts

No prompt is trusted without runtime validation.

---

# Platform

The platform exposes:

- CLI
- MCP
- Studio
- SDK
- Marketplace
- Plugin System

Every interface consumes the same Runtime contracts.

---

# Success Criteria

OpenContext succeeds when:

- first-run experience is excellent;
- engineering work is reproducible;
- execution is observable;
- context remains minimal;
- quality is benchmarked;
- extensibility remains safe.

---

# Architectural Invariants

- Runtime before prompts.
- Contracts before implementations.
- Evidence before assumptions.
- Local validation before inference.
- Benchmarks before promotion.
- Compatibility before rewrites.

---

# Final Statement

This document summarizes the complete OpenContext architecture.

The detailed behaviour of every subsystem is defined by the accompanying architecture documents.
