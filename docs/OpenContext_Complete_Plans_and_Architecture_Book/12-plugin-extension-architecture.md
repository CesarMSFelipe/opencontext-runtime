# OpenContext Plugin & Extension Architecture
## Version 1.0 (Draft)
### Document ID
OC-PLUGIN-001

## Purpose

This document defines the extension model for OpenContext.

Everything that is not part of the Runtime Core should be extensible through stable contracts.

---

# Design Principles

- Runtime Core remains minimal.
- Plugins extend, never patch.
- Public contracts are versioned.
- Extensions are permissioned.
- Runtime validates compatibility.
- Plugins are benchmarkable.
- Plugins are sandbox-aware.

---

# Extension Points

Plugins may contribute:

- Workflows
- Personas
- Skills
- Harnesses
- Policies
- Providers
- Knowledge Graph providers
- Memory providers
- Context strategies
- Runtime Intelligence analyzers
- Studio panels
- CLI commands
- MCP tools
- Project templates
- Benchmark suites

---

# Plugin Manifest

```yaml
schema_version: opencontext.plugin.v1
id: opencontext.drupal
version: 1.0.0
name: Drupal Toolkit

requires:
  runtime: ">=2.0"

contributes:
  workflows: []
  personas:
    - oc-drupal-engineer
  skills:
    - drupal-service-review
  harnesses: []
  providers: []
```

---

# Plugin Lifecycle

```text
Discover
↓
Validate
↓
Resolve Dependencies
↓
Permission Check
↓
Register Contributions
↓
Activate
↓
Health Check
```

---

# Contracts

Every plugin contribution must implement a public contract.

Examples:

- WorkflowDefinition
- PersonaDefinition
- SkillDefinition
- HarnessDefinition
- Provider
- MemoryProvider
- KnowledgeProvider

Internal Runtime APIs are never exposed.

---

# Compatibility

Plugins declare:

- minimum runtime version
- supported API version
- optional features
- required capabilities

Incompatible plugins remain disabled.

---

# Security

Plugins execute under Runtime Policy.

Restricted operations include:

- filesystem writes
- network access
- process execution
- provider usage
- memory writes
- KG writes

Permissions are explicit.

---

# Benchmarks

Plugins should ship benchmark suites.

Installation should optionally execute plugin benchmarks to validate behaviour before activation.

---

# Configuration

```yaml
plugins:
  auto_discovery: true
  auto_update: false
  require_signatures: false
  benchmark_on_install: true
```

---

# Migration

Existing built-in components should gradually move to the same public contracts used by plugins.

If the Runtime can load a built-in component, it should also be able to load an external one.

---

# Invariants

1. Plugins never bypass Runtime.
2. Plugins use stable contracts.
3. Plugins cannot modify Runtime Core.
4. Plugin permissions are enforced.
5. Plugin failures are isolated.
6. Plugin contributions are observable.
7. Plugin APIs are versioned.

---

# Definition of Done

Implemented when:

- Plugin Registry exists.
- Public contracts are documented.
- Runtime discovers plugins.
- Plugins register safely.
- Version compatibility works.
- Security policies apply.
- Benchmarks validate plugins.

---

# Final Statement

OpenContext should become a platform, not a monolith.

Every major capability should be replaceable without modifying the Runtime Core.
