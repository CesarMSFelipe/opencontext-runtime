# OpenContext Architecture Maturity Model
## Version 1.0 (Draft)
### Document ID
OC-MATURITY-001

# Purpose

This document defines a maturity model for OpenContext deployments, allowing projects and organizations to measure adoption objectively.

---

# Level 0 — Assisted Prompting

Characteristics:

- Chat-based usage
- No Runtime governance
- No Knowledge Graph
- No Memory
- Manual workflows

---

# Level 1 — Managed Runtime

Requirements:

- Runtime
- Sessions
- Artifacts
- Receipts
- Policy Engine
- Local Inspection

Success criteria:

- Repeatable execution
- Observable runs
- Basic governance

---

# Level 2 — Engineering Runtime

Requirements:

- SDD
- OC Flow
- Workflow Registry
- Personas
- Skills
- Harnesses
- Capability Registry

Success criteria:

- Deterministic engineering workflows
- Low token waste
- First-run success

---

# Level 3 — Cognitive Engineering

Requirements:

- Knowledge Graph
- Memory
- Context Engineering
- Semantic Compression
- Runtime Intelligence

Success criteria:

- Context budgets enforced
- Durable project knowledge
- Intelligent workflow selection

---

# Level 4 — Platform

Requirements:

- Plugin SDK
- Marketplace
- Studio
- Public Contracts
- Benchmark Framework

Success criteria:

- Safe extensibility
- Rich ecosystem
- Visual observability

---

# Level 5 — Enterprise

Requirements:

- Organization Graph
- Distributed Runtime
- Multi-repository support
- Enterprise Policy
- RBAC
- Audit
- Fleet Management

Success criteria:

- Organization-wide governance
- Shared knowledge
- Scalable execution

---

# Level 6 — Adaptive Platform

Requirements:

- Research framework
- Experiment registry
- Automated evaluations
- Feature flags
- Evidence-driven evolution

Success criteria:

- Continuous improvement
- Architecture evolves through benchmarks
- Stable public contracts

---

# Assessment Matrix

Each capability is scored:

- Not Started
- Experimental
- Operational
- Production
- Optimized

Overall maturity equals the lowest critical capability across Runtime, Governance, Cognitive Layer and Platform.

---

# CLI

```bash
opencontext maturity assess
opencontext maturity report
```

---

# Studio

Studio should display:

- current maturity level
- missing capabilities
- recommended next milestones
- benchmark coverage

---

# Definition of Done

Implemented when:

- maturity assessment exists;
- reports are generated;
- Studio visualizes maturity;
- roadmap links to maturity improvements.

---

# Final Statement

The maturity model provides a measurable path from a simple engineering assistant to a fully governed Engineering Operating System.
