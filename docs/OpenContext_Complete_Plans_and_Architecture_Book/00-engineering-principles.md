# OpenContext Engineering Constitution
## Version 1.0 (Draft)

### Document ID
OC-CONSTITUTION-001

### Status
Draft

### Applies to
This document governs every subsystem of OpenContext, including Runtime, SDD Workflow, OC Flow, Knowledge Graph, Memory, Semantic Compression, Context Engineering, Skills, Personas, Harnesses, Runtime Intelligence, Studio, Plugin SDK, CLI, MCP Integration, Providers, Benchmarks, and Policies.

Every future component MUST comply with this document unless an Architecture Decision Record (ADR) explicitly documents an approved exception.

---

# 1. Purpose

OpenContext exists to become the Engineering Operating System for AI-assisted software development.

Its purpose is not to automate software engineering.

Its purpose is to reduce uncertainty during software engineering.

Every subsystem exists to increase correctness, explainability and engineering quality while minimizing unnecessary cognitive and computational cost.

The runtime is not the product.

The engineering process is the product.

---

# 2. Vision

OpenContext should become the reference platform for deterministic agentic engineering.

Instead of replacing engineering discipline with autonomous reasoning, OpenContext augments engineering discipline through structured workflows, deterministic execution, governed context and measurable decision making.

The platform should make software engineering more predictable, reproducible, observable, cheaper, safer, and easier to understand.

The ideal OpenContext session should feel less like interacting with a chatbot and more like collaborating with an experienced engineering team operating under a rigorous methodology.

---

# 3. Mission

Every task executed by OpenContext should answer five questions:

1. What problem are we solving?
2. Why is this the correct solution?
3. What evidence supports this decision?
4. What did the runtime actually do?
5. How can this knowledge improve future executions?

If any of these questions cannot be answered, the execution is considered incomplete.

---

# 4. Product Philosophy

OpenContext is not a prompt framework.

OpenContext is not a coding agent.

OpenContext is not a chat interface.

OpenContext is an Engineering Operating System.

The LLM is only one component of the system.

The primary responsibility for correctness belongs to the runtime architecture, not to the language model.

---

# 5. Engineering Principles

## Principle 1 — Reduce uncertainty, not maximize autonomy

The purpose of AI is not to perform more actions.

The purpose of AI is to perform better informed actions.

Autonomy without evidence increases risk.

Evidence reduces uncertainty.

Therefore every subsystem should prioritise evidence gathering before autonomous behaviour.

## Principle 2 — Evidence before reasoning

The runtime must always prefer obtaining evidence over speculative reasoning.

Correct execution order:

```text
Observe
↓
Retrieve
↓
Verify
↓
Reason
↓
Act
↓
Verify
```

Incorrect execution order:

```text
Think
↓
Guess
↓
Search afterwards
```

No reasoning step should be performed if relevant evidence can still be collected.

## Principle 3 — Context is a liability

Context is not inherently valuable.

Every additional token introduces latency, cost, ambiguity, hallucination risk, and distraction.

The objective is never to maximise context.

The objective is to minimise context while preserving correctness.

Success is measured by useful information density.

## Principle 4 — Local before LLM

Any deterministic operation must be executed locally before involving a language model.

Examples include AST parsing, Tree-Sitter, ripgrep, Git, linters, static analysis, Knowledge Graph queries, semantic search, policy evaluation, and configuration inspection.

The LLM should only solve problems that cannot reasonably be solved through deterministic computation.

## Principle 5 — Deterministic before agentic

If two approaches produce equivalent outcomes, the deterministic solution always wins.

Agentic reasoning is a scarce resource.

It should be reserved for ambiguity, creativity and decision making.

Never for simple computation.

## Principle 6 — Smallest context wins

Every retrieval operation should minimise files, symbols, documents, conversations, memories and prompts.

No component should retrieve information merely because it might be useful.

Information should only be retrieved when evidence suggests it is necessary.

## Principle 7 — Every expensive decision requires evidence

High-cost operations include workflow switches, deep retrieval, repository exploration, broad mutations, multiple LLM calls, and long-running diagnosis.

Every expensive decision must generate evidence, rationale, expected benefit, estimated cost, and receipt.

## Principle 8 — Fail small

Large failures are architecture failures.

The runtime should prefer:

```text
small mutation
↓
local verification
↓
next mutation
```

instead of:

```text
large mutation
↓
hope
↓
debug everything
```

Small failures are easier to diagnose.

## Principle 9 — Verify continuously

Verification is not a phase.

Verification is continuous.

Every meaningful action should produce immediate validation whenever possible.

The runtime should prefer many inexpensive validations over one expensive validation at the end.

## Principle 10 — Learn only durable knowledge

Not every execution deserves memory.

Only knowledge that is reusable, verified, stable and valuable should become long-term memory.

Everything else is execution noise.

---

# 6. Context Principles

Context is a service.

Context is never the objective.

Every context retrieval must answer:

- Why is this information required?
- What decision depends on it?
- When can it be discarded?

Context should always be minimal, evidence-backed, attributable, compressible and replaceable.

---

# 7. Memory Principles

Memory exists to prevent repeated engineering work.

Memory must never become historical clutter.

Memory should remember decisions, conventions, procedures, validated failures and successful strategies.

Memory should never store chain of thought, speculative reasoning, temporary conversations, duplicated source code or transient failures.

---

# 8. Knowledge Graph Principles

The Knowledge Graph is the source of engineering truth.

The graph represents structure, dependencies, ownership, contracts, relationships and evolution.

The graph should answer engineering questions without requiring repository exploration whenever possible.

The graph is authoritative for structure.

Source code is authoritative for implementation.

---

# 9. Workflow Principles

Workflows exist to reduce engineering risk.

Different workflows optimise different trade-offs.

No workflow is universally correct.

Workflow selection must be based on scope, confidence, cost, risk and evidence.

Never on user habit.

---

# 10. Harness Principles

Harnesses are engineering components.

They are not prompts.

Each harness must be deterministic, observable, benchmarked, configurable, replaceable and measurable.

Harnesses exist to enforce engineering discipline.

Not to compensate for poor prompts.

---

# 11. Skill Principles

Skills represent reusable engineering behaviour.

A skill should describe when to execute, when not to execute, required inputs, expected outputs, gates, receipts and failure modes.

Skills must remain independent.

No skill should contain hidden workflow logic.

---

# 12. Persona Principles

Personas represent engineering responsibilities.

They do not represent personalities.

Every persona owns a domain of expertise.

Responsibilities must never overlap unnecessarily.

Multiple personas may collaborate.

None should duplicate another.

---

# 13. Runtime Principles

The runtime coordinates engineering.

It does not replace engineering judgement.

The runtime should orchestrate, observe, verify, explain and optimise.

It should never hide important decisions.

---

# 14. UX Principles

The user should always understand what happened, why it happened, what evidence supports it, what changed and what remains uncertain.

The runtime should surprise users with quality.

Never with hidden behaviour.

---

# 15. Security Principles

Security is proactive.

Not reactive.

Every security-sensitive operation must be explicitly recognised before execution.

The runtime must assume that credentials exist, production systems matter, and repositories contain valuable assets.

Safety takes priority over convenience.

---

# 16. Performance Principles

Performance is measured globally.

Not by model speed.

Relevant metrics include engineering time, success rate, token cost, local computation, retries, correctness and maintainability.

Fast incorrect execution is failure.

---

# 17. Observability Principles

Every significant action should leave evidence.

Every execution should be reconstructable.

Every decision should be explainable.

If an engineer cannot understand why something happened after the execution, observability is insufficient.

---

# 18. Evolution Principles

OpenContext should evolve through evidence.

Not intuition.

Every optimisation proposal must demonstrate measurable improvement through benchmarks before adoption.

No subsystem may self-modify without validation.

---

# 19. Plugin Principles

Everything should be replaceable.

Every major subsystem should expose stable contracts.

Internal implementation should never become mandatory for extension.

Plugins should integrate through contracts.

Never through implementation details.

---

# 20. Decision Hierarchy

Whenever multiple alternatives exist, OpenContext follows this order of preference:

1. Deterministic computation
2. Local tooling
3. Knowledge Graph
4. Memory
5. Structured retrieval
6. Agentic reasoning
7. Human escalation

Higher levels should only be used when lower levels cannot solve the problem.

---

# 21. Non Goals

OpenContext does not aim to maximise autonomy, replace software engineers, maximise prompt size, memorise repositories, hide engineering decisions, optimise for demos over production, or depend on a specific model provider.

---

# 22. Definition of Quality

A successful execution is one that:

- solved the intended problem
- used the minimum sufficient context
- minimised unnecessary LLM reasoning
- verified its own work
- produced engineering evidence
- generated reproducible artefacts
- improved future executions
- remained explainable

Anything less is an incomplete execution.

---

# 23. Constitutional Rule

Every future feature proposed for OpenContext MUST answer the following questions before implementation:

1. Which engineering principle does it reinforce?
2. Which subsystem owns it?
3. Which measurable problem does it solve?
4. How is success benchmarked?
5. Which evidence validates its behaviour?
6. Which existing capability cannot already solve the same problem?
7. Does it reduce uncertainty?
8. Does it reduce engineering effort?
9. Does it improve correctness?
10. Does it preserve simplicity?

If these questions cannot be answered satisfactorily, the feature should not be implemented.

---

# 24. Final Statement

OpenContext is built on one fundamental belief:

> Better engineering does not come from making larger agents.

It comes from building better engineering systems.

Every line of code, every workflow, every skill, every harness, every piece of memory and every future capability must exist for one reason only:

**To help engineers make better decisions with less uncertainty, lower cost and stronger evidence.**
