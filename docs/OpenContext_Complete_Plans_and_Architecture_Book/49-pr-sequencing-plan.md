# OpenContext PR Sequencing Plan
## Version 1.0 (Draft)
### Document ID
OC-PRPLAN-001

# Purpose

This document converts the architecture and epic roadmap into an incremental pull request strategy that can be applied to the current `feat/agentic-engineering-runtime` branch.

The objective is to reach OpenContext 1.0 without disruptive rewrites, preserving compatibility while continuously improving the Runtime.

---

# Principles

1. Small, reviewable PRs.
2. Backward compatibility by default.
3. Every PR ships with tests.
4. Every PR references architecture documents.
5. Every PR leaves the project releasable.
6. Feature flags protect unfinished capabilities.

---

# PR Sequence

## PR-001 — Runtime Core
- RuntimeSession
- RuntimeRun
- EventBus
- StateMachine
- Tests

Depends on: none

## PR-002 — Artifacts & Receipts
- ArtifactStore
- ReceiptStore
- Checkpoints
- Resume
- Rollback

Depends on: PR-001

## PR-003 — Workflow Registry
- WorkflowDefinition
- WorkflowRegistry
- Register current SDD
- Compatibility aliases

Depends on: PR-001

## PR-004 — SDD Hardening
- Fix propose/apply flow
- Explicit phase outputs
- Better harness integration

Depends on: PR-003

## PR-005 — Policy Engine
- Policy registry
- File policy
- Command policy
- Provider policy

Depends on: PR-001

## PR-006 — Persona/Skill/Harness Registries

Depends on:
- PR-003
- PR-005

## PR-007 — OC Flow

Implements:

- init
- gather_context
- plan
- mutate
- inspection
- diagnose
- escalation
- consolidation

Depends on:
- PR-006

## PR-008 — Knowledge Graph v2

Depends on:
- PR-007

## PR-009 — Memory v2

Depends on:
- PR-008

## PR-010 — Context Engine v2

Depends on:
- PR-008
- PR-009

## PR-011 — Runtime Intelligence

Depends on:
- PR-010

## PR-012 — Provider Gateway

Depends on:
- PR-011

## PR-013 — CLI/MCP Modernization

Depends on:
- PR-012

## PR-014 — Studio MVP

Depends on:
- PR-013

## PR-015 — Plugin SDK

Depends on:
- PR-014

## PR-016 — Marketplace

Depends on:
- PR-015

## PR-017 — Benchmarks & Release

Depends on all previous PRs.

---

# Acceptance Criteria

Every PR must include:

- Architecture references
- Updated contracts
- Unit tests
- Benchmark updates where applicable
- Documentation updates
- Migration notes if required

---

# Release Milestones

Milestone A:
- Runtime foundation

Milestone B:
- Stable SDD

Milestone C:
- OC Flow beta

Milestone D:
- Cognitive Runtime

Milestone E:
- Platform

Milestone F:
- OpenContext 1.0

---

# Final Statement

The architecture should be implemented through incremental, benchmark-driven pull requests rather than large rewrites.
