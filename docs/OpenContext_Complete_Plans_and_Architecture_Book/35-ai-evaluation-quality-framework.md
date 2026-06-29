# OpenContext AI Evaluation & Quality Framework
## Version 1.0 (Draft)
### Document ID
OC-EVALS-001

# Purpose

This document defines the evaluation framework used to continuously measure the quality of OpenContext.

Unlike traditional testing, evaluations measure engineering outcomes produced by the Runtime.

---

# Objectives

The framework must answer:

- Did the Runtime solve the task?
- Was the selected workflow appropriate?
- Was context sufficient but minimal?
- Were unnecessary model calls avoided?
- Did harnesses prevent bad changes?
- Was the final patch maintainable?
- Was token usage acceptable?

---

# Evaluation Categories

- Functional correctness
- Architectural quality
- Context efficiency
- Token efficiency
- Runtime governance
- Safety & policy
- Knowledge Graph quality
- Memory quality
- Developer experience
- First-run experience

---

# Canonical Evaluation Suites

## First Run

Measures installation-to-success experience.

## Bug Fix

Localized OC Flow tasks.

## Feature Delivery

End-to-end SDD execution.

## Large Repository

Navigation and context quality.

## Security Review

Policy and harness effectiveness.

## Regression

Historical tasks replayed across releases.

---

# Metrics

Each evaluation records:

- success_rate
- token_count
- latency
- retries
- workflow_selected
- confidence
- escalation_rate
- patch_size
- local_validation_pass_rate
- benchmark_version

---

# Evaluation Records

Evaluations are immutable artifacts.

They include:

- task
- repository
- workflow
- runtime version
- provider
- configuration profile
- receipts
- benchmark outputs

---

# Continuous Quality

Every release compares against the previous stable baseline.

Regressions require:

- investigation
- ADR if architectural
- mitigation plan

---

# CI Gates

Minimum gates:

- no first-run regression
- no workflow regression
- no benchmark regression beyond threshold
- no policy regression

---

# Studio

Studio should visualize:

- quality trends
- benchmark deltas
- regression history
- workflow comparison
- token trends

---

# CLI

```bash
opencontext eval run
opencontext eval compare
opencontext eval report
```

---

# Invariants

1. Quality is measured continuously.
2. Benchmark methodology is versioned.
3. Regressions are visible.
4. Evaluations use public contracts.
5. Quality claims require evidence.

---

# Definition of Done

Implemented when:

- evaluation registry exists;
- evaluation artifacts are generated;
- CI consumes evaluation results;
- Studio renders quality history;
- release process depends on evaluation outcomes.

---

# Final Statement

OpenContext should improve because it measures engineering quality objectively, not because it assumes newer is better.
