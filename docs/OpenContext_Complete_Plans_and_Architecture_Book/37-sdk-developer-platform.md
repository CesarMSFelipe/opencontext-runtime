# OpenContext SDK & Developer Platform Blueprint
## Version 1.0 (Draft)
### Document ID
OC-SDK-001

# Purpose

This document defines the SDK and developer platform strategy for OpenContext.

The SDK exists so contributors, plugin authors and enterprise teams can extend OpenContext without depending on internal Runtime implementation details.

---

# Mission

The OpenContext SDK should make it easy to build:

- workflows
- skills
- personas
- harnesses
- providers
- KG providers
- memory providers
- policies
- evaluators
- benchmarks
- Studio panels
- CLI extensions
- MCP tools

while preserving Runtime governance, safety and compatibility.

---

# Core Principles

1. Public contracts before internal APIs.
2. Stable schemas before convenience helpers.
3. Plugins never patch Runtime Core.
4. SDK validation is mandatory.
5. Generated scaffolds follow best practices.
6. Extension permissions are explicit.
7. SDK examples are executable.
8. Compatibility is machine-checkable.
9. Testing and benchmarking are built in.
10. The SDK teaches the architecture.

---

# SDK Layers

```text
opencontext-sdk
  contracts
  plugin authoring
  validation
  testing
  benchmark helpers
  provider helpers
  studio panel helpers
  CLI scaffolding
```

---

# SDK Packages

Possible packages:

```text
opencontext-sdk-core
opencontext-sdk-testing
opencontext-sdk-studio
opencontext-sdk-provider
opencontext-sdk-plugin
```

Python package layout:

```text
opencontext_sdk/
  contracts/
  plugins/
  skills/
  personas/
  harnesses/
  providers/
  memory/
  kg/
  testing/
  benchmarks/
  studio/
  cli/
```

---

# Contract Exports

The SDK exports public contracts:

- WorkflowDefinition
- PersonaDefinition
- SkillDefinition
- HarnessDefinition
- PluginManifest
- RuntimeEvent
- ArtifactRef
- Receipt
- ContextEnvelope
- MemoryRecord
- KgNode
- KgEdge
- PolicyDecision
- BenchmarkTask
- BenchmarkResult

---

# Scaffolding

SDK provides generators:

```bash
opencontext sdk create plugin my-plugin
opencontext sdk create skill oc-my-skill
opencontext sdk create harness my-harness
opencontext sdk create provider my-provider
opencontext sdk create studio-panel my-panel
```

Generated code must include:

- manifest
- tests
- benchmark scaffold
- docs
- examples
- permissions

---

# Validation

SDK validation commands:

```bash
opencontext sdk validate plugin
opencontext sdk validate contracts
opencontext sdk validate permissions
opencontext sdk validate benchmarks
```

Validation checks:

- schema correctness
- contract compatibility
- dependency resolution
- permission declarations
- missing benchmarks
- unsafe defaults

---

# Testing Helpers

The SDK provides helpers for:

- fake Runtime sessions
- fake KG
- fake Memory
- mock Provider Gateway
- policy test harness
- artifact test store
- benchmark fixtures

---

# Benchmark Helpers

Plugins should be benchmarkable.

SDK provides:

- benchmark runner helpers
- fixture loading
- metric collection
- baseline comparison
- report generation

---

# Provider SDK

Provider adapters implement:

```python
class ProviderAdapter:
    def capabilities(self) -> ProviderCapabilities: ...
    def complete(self, request: ProviderRequest) -> ProviderResponse: ...
    def stream(self, request: ProviderRequest) -> Iterator[ProviderChunk]: ...
```

Adapters must report:

- token usage
- cost
- latency
- model identity
- structured output support

---

# Harness SDK

Harness plugins implement:

```python
class HarnessPlugin:
    def definition(self) -> HarnessDefinition: ...
    def run(self, request: HarnessRunRequest) -> HarnessResult: ...
```

Harnesses must not mutate files unless explicitly allowed and routed through Runtime mutation APIs.

---

# Skill SDK

Skill plugins provide:

- SkillDefinition
- compact rules
- input schema
- output schema
- benchmark tasks
- examples

Skills do not own execution.

---

# Studio SDK

Studio panels consume public contracts only.

Panels may visualize:

- artifacts
- receipts
- KG subgraphs
- memory
- benchmarks
- policy decisions
- plugin-specific reports

Studio panels cannot execute Runtime operations directly.

---

# Documentation Generation

The SDK should generate documentation from manifests and contracts.

```bash
opencontext sdk docs generate
```

Generated docs include:

- plugin overview
- permissions
- provided components
- examples
- benchmark results

---

# Compatibility

SDK includes compatibility checks:

```bash
opencontext sdk compat --runtime 1.0
```

Checks:

- contract versions
- deprecated APIs
- plugin manifest compatibility
- schema changes

---

# Security

SDK defaults are safe.

Generated plugins request no permissions by default.

Developers must explicitly add permissions.

---

# Distribution

SDK packages should be versioned with OpenContext.

Stable contracts are maintained across minor versions.

---

# Invariants

1. SDK uses public contracts only.
2. SDK examples are runnable.
3. Generated plugins are safe by default.
4. Validation is available locally.
5. Benchmarks are part of plugin development.
6. Studio panels cannot bypass Runtime.
7. Provider adapters report usage.
8. Harnesses return HarnessResult.
9. Skills return typed outputs.
10. Compatibility is machine-checkable.

---

# Definition of Done

SDK is ready when:

- plugin scaffold works;
- skill scaffold works;
- harness scaffold works;
- provider scaffold works;
- Studio panel scaffold works;
- validation commands work;
- test helpers exist;
- benchmark helpers exist;
- docs generation works;
- compatibility checks work.

---

# Final Statement

The SDK is how OpenContext becomes a platform.

A powerful architecture only becomes an ecosystem when others can extend it safely.
