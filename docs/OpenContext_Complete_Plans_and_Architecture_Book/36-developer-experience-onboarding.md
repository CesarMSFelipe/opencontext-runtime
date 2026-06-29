# OpenContext Developer Experience & Onboarding Blueprint
## Version 1.0 (Draft)
### Document ID
OC-DX-001

# Purpose

This document defines the developer experience strategy for OpenContext.

Developer Experience covers the journey from first install to productive daily use, contribution, debugging, extension development and enterprise adoption.

---

# Mission

OpenContext should feel powerful without feeling complex.

A new user should be able to:

```bash
opencontext init
opencontext doctor
opencontext index
opencontext run "Fix failing test"
```

and receive a useful, understandable result.

A contributor should be able to understand where to implement a change by reading the architecture documents and running focused tests.

A plugin author should be able to build extensions using stable contracts without reading Runtime internals.

---

# Core Principles

1. First success matters.
2. Defaults should be excellent.
3. Advanced power should be progressively disclosed.
4. Errors should be actionable.
5. Every command should explain the next useful step.
6. Documentation should match real CLI/MCP behaviour.
7. Debugging should be artifact-driven.
8. Contributors should not need implicit project knowledge.
9. Plugins should be easy to build safely.
10. The system should teach users how it works.

---

# User Personas

## First-Time User

Goal:

- install OpenContext;
- run first task;
- trust the output.

Needs:

- simple init;
- clear doctor;
- useful defaults;
- actionable errors.

## Daily Developer

Goal:

- run OC Flow and SDD tasks;
- inspect results;
- resume work;
- trust patches.

Needs:

- fast CLI;
- clear artifacts;
- good summaries;
- predictable workflows.

## Maintainer

Goal:

- review changes;
- preserve architecture;
- manage releases.

Needs:

- governance docs;
- benchmarks;
- ADRs;
- contract validation.

## Plugin Author

Goal:

- create skills, harnesses, personas, providers or Studio panels.

Needs:

- SDK;
- manifests;
- examples;
- validation tools.

## Enterprise Admin

Goal:

- configure policy, providers, plugins and governance.

Needs:

- profiles;
- audit;
- RBAC;
- observability;
- data governance.

---

# First-Run Journey

The first-run journey should be:

```text
Install
↓
Init
↓
Doctor
↓
Index
↓
Run task
↓
Review result
↓
Learn next command
```

Every step should explain success, warnings and next action.

---

# CLI UX Requirements

Commands should provide:

- concise human summary;
- artifact links;
- next recommended command;
- machine-readable JSON option;
- actionable error messages.

Example:

```text
Workflow selected: OC Flow
Reason: localized bugfix with available tests
Changed: 1 file
Verified: targeted tests passed
Artifacts: patch.diff, inspection-report.json
Next: review patch and commit
```

---

# Error Message Standard

Every error should include:

- what failed;
- why it failed;
- whether it is recoverable;
- next action;
- relevant artifact path.

Bad:

```text
Failed.
```

Good:

```text
Inspection failed because no test command was detected.
Add `inspection.tests.command` to opencontext.yaml or run `opencontext doctor --fix`.
```

---

# Documentation Experience

Docs should include:

- quickstart;
- conceptual overview;
- workflow guide;
- configuration guide;
- plugin guide;
- troubleshooting;
- architecture book;
- API contracts;
- examples.

Docs must be generated or validated against actual schemas where possible.

---

# Example Projects

OpenContext should maintain example projects:

- Python simple
- TypeScript simple
- PHP/Symfony
- Drupal
- Monorepo
- Plugin example
- Enterprise config example

Each example should include benchmark tasks.

---

# Contributor Experience

Contributors should be able to run:

```bash
opencontext dev doctor
opencontext dev test
opencontext dev benchmark smoke
opencontext dev validate-contracts
```

---

# Plugin Author Experience

Plugin scaffolding:

```bash
opencontext plugin create my-plugin
opencontext plugin validate
opencontext plugin benchmark
```

Plugin examples should include:

- skill plugin;
- persona plugin;
- harness plugin;
- provider plugin;
- Studio panel plugin.

---

# Debugging Experience

Debugging should rely on:

- session status;
- events;
- artifacts;
- receipts;
- traces;
- live state;
- Studio.

Command:

```bash
opencontext debug <session_id>
```

Should summarize:

- last failure;
- blocking gate;
- relevant artifact;
- next action.

---

# Onboarding Quality Gates

OpenContext first-run onboarding is acceptable only if:

- init completes without advanced choices;
- doctor detects capabilities;
- index succeeds or degrades clearly;
- run produces a useful summary;
- missing tools produce actionable guidance;
- artifacts are easy to find.

---

# Invariants

1. First-run path is protected by benchmarks.
2. Documentation reflects actual behaviour.
3. Errors are actionable.
4. Advanced options are not required for first success.
5. Debugging uses artifacts, not hidden logs.
6. Plugin creation is scaffolded.
7. Contributors have validation commands.
8. Users always see next action.

---

# Definition of Done

Implemented when:

- quickstart works;
- init/doctor/index/run path is smooth;
- developer commands exist;
- plugin scaffolding exists;
- examples exist;
- troubleshooting docs exist;
- first-run benchmark includes UX assertions.

---

# Final Statement

Developer Experience is not cosmetic.

For OpenContext, good DX is how the system earns trust before users understand the full architecture.
