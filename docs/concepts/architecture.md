# Architecture

## Purpose
Core is provider/framework agnostic. API and CLI are thin adapters. Technology profiles live outside core. Safety, ranking, packing, prompt assembly, memory usability, and traces are core interfaces or deterministic implementations.

## Current Status
Implemented around a strict boundary: `opencontext_core` owns domain logic and deterministic local
runtime behavior; API, CLI, profiles, and provider adapters sit above it. Core includes indexing,
repo maps, dependency graphs, retrieval, ranking, packing, compression, prompt assembly, safety,
memory usability, traces, workflows, controlled harness planning, and provider-neutral interfaces.

FastAPI, CLI behavior, provider SDKs, framework-specific profiles, and external storage adapters do
not belong in core.

## Related Commands
```bash
opencontext doctor runtime
opencontext doctor deep
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/` (domain logic and deterministic local runtime)
- `packages/opencontext_core/opencontext_core/adapters/` (provider-neutral interfaces)
- `packages/{opencontext_api,opencontext_cli,opencontext_profiles}/` (adapters above core)
