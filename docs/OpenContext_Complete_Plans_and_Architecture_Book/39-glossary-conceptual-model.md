# OpenContext Glossary & Conceptual Model
## Version 1.0 (Draft)
### Document ID
OC-GLOSSARY-001

# Purpose

This document defines the shared vocabulary used across the OpenContext architecture documents.

A consistent vocabulary is required so contributors, plugin authors, users and maintainers can reason about the system without ambiguity.

---

# Core Concepts

## OpenContext

An Engineering Operating System for AI-assisted software development.

OpenContext is composed of Runtime, Workflows, Knowledge Graph, Memory, Context Engineering, Skills, Personas, Harnesses, Policies, Observability, Runtime Intelligence, Studio and Plugin SDK.

## Runtime

The execution core of OpenContext.

It owns sessions, runs, workflow execution, state transitions, events, artifacts, receipts, policies and consolidation.

## Workflow

A declarative engineering process executed by the Runtime.

Examples:

- SDD
- OC Flow
- Review
- Benchmark

## SDD

Software Design Driven workflow.

A formal workflow for high-risk or architecture-sensitive engineering tasks.

## OC Flow

OpenContext Flow.

A fast operational workflow for bugfixes, small refactors, maintenance and first-run success.

## Session

The top-level execution container for a user task.

A session may contain one or more runs.

## Run

One execution of one workflow inside a session.

## Node

A workflow step.

Examples:

- gather_context
- plan
- mutate
- local_inspection
- diagnose

## Persona

An engineering responsibility used by workflow nodes.

Personas are not personalities.

Examples:

- Architect
- Builder
- Diagnostician
- Reviewer

## Skill

A reusable engineering capability invoked by personas.

Skills have inputs, outputs, gates, budgets and contracts.

## Harness

A deterministic governance component that validates or controls engineering behaviour.

Examples:

- Context Harness
- Mutation Harness
- Inspection Harness
- Diagnosis Harness
- Security Harness

## Knowledge Graph

A typed, evidence-backed graph of code structure, dependencies, tests, ownership, decisions and runtime experience.

## Memory

Durable project knowledge learned across sessions.

Memory is not chat history.

## Context Engineering

The process of retrieving, compressing and delivering the minimum sufficient context for a workflow node.

## Context Envelope

A structured context package containing L1/L2/L3 context, evidence, omissions and token budget.

## L1 Context

Ephemeral working context.

Includes focused snippets, diagnostics and immediate task data.

## L2 Context

Task contract.

Includes acceptance criteria, constraints and verification plan.

## L3 Context

Structural context.

Includes KG-derived signatures, owners, dependencies and architectural facts.

## Artifact

A durable output created by the Runtime.

Examples:

- patch
- spec
- design
- inspection report
- summary

## Receipt

A durable proof of a decision or action.

Examples:

- workflow selection receipt
- mutation receipt
- policy receipt

## Policy

A runtime-enforced rule governing what OpenContext may read, write, execute, remember or expose.

## Capability

A detected environmental ability.

Examples:

- git
- pytest
- phpstan
- docker
- KG index
- host sampling

## Provider

A model or service backend accessed through Provider Gateway.

Examples:

- chat model
- embedding model
- reranker
- local model

## Provider Gateway

The abstraction that routes model/service calls based on capabilities, cost, policy and workflow needs.

## Runtime Intelligence

The layer responsible for cost estimation, confidence scoring, simulation, profiling, benchmarks, health and evolution proposals.

## Studio

The visual control plane for OpenContext.

Studio observes sessions, events, artifacts, receipts, KG, memory, cost, confidence and benchmarks.

## Plugin

An extension package that contributes workflows, personas, skills, harnesses, providers, policies, evaluators, KG providers, memory providers or Studio panels.

## Public Contract

A versioned schema or API that external components may depend on.

## ADR

Architecture Decision Record.

A durable record of a significant architecture decision.

## Benchmark

A repeatable evaluation that measures runtime quality, correctness, cost or safety.

## First-Run Benchmark

A benchmark proving that a new user can install OpenContext and complete a useful first task.

## Escalation

A governed stop condition that produces a human handoff when the Runtime cannot safely continue.

## Consolidation

The final workflow stage that archives artifacts, writes memory candidates, updates KG and produces summaries.

## Semantic Compression

Compression that preserves engineering meaning while reducing tokens.

## Semantic GC

Garbage collection of redundant or obsolete context, logs and intermediate reasoning.

## ApplyEdit

A structured mutation operation used to edit code surgically.

## Checkpoint

A pre-mutation snapshot used for rollback.

## Rollback

Restoration of checkpointed state after failure or rejection.

## Profile

A configuration preset.

Examples:

- balanced
- low-cost
- enterprise
- research
- performance

## Marketplace

A registry of installable OpenContext extension packages.

## Organization Graph

The graph of teams, owners, services, systems, runbooks, policies and escalation paths.

---

# Conceptual Relationships

```text
User Task
  -> Session
    -> Run
      -> Workflow
        -> Node
          -> Persona
            -> Skills
              -> Harnesses
                -> Tools / KG / Memory / Providers
```

---

# Key Distinctions

## Workflow vs Runtime

Workflow describes process.

Runtime executes process.

## Persona vs Skill

Persona owns responsibility.

Skill performs reusable procedure.

## Skill vs Harness

Skill helps perform work.

Harness validates or governs work.

## KG vs Memory

KG stores structure and relationships.

Memory stores durable learned knowledge.

## Artifact vs Receipt

Artifact is what was produced.

Receipt is why/how it was produced.

## Studio vs Runtime

Studio observes.

Runtime executes.

---

# Invariants

1. Use these terms consistently.
2. Do not use agent/persona interchangeably without precision.
3. Do not call memory chat history.
4. Do not call harnesses prompts.
5. Do not call artifacts receipts.
6. Do not call workflows runtimes.
7. Do not call Studio the executor.

---

# Final Statement

A precise architecture requires a precise vocabulary.

This glossary is part of the architecture, not an appendix.
