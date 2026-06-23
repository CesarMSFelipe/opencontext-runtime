# Architecture Overview

OpenContext Runtime is organized around a strict dependency direction:

```text
Adapters / Integrations
        |
Workflow Packs
        |
Technology Profiles
        |
OpenContext Core
```

The core package owns project indexing, memory abstractions, retrieval, context
optimization, cache interfaces, safety scanning, tool registry boundaries,
evaluation skeletons, workflow execution, LLM gateway interfaces, and traces.
Adapter packages are thin entry points that call the core runtime.

`opencontext_core` is technology-agnostic. It defines the `TechnologyProfile`
interface, but does not contain Drupal, Symfony, Node, Python, Java, or other
framework-specific logic. First-party profiles live above the core in
`opencontext_profiles` for v0.1 so they can later be split into independent
packages such as `opencontext_profile_drupal` or `opencontext_profile_python`.

Drupal is an important first-party profile, not a core dependency.

## Core Responsibilities

- Index projects into manifests, file metadata, symbols, dependency graphs, and repo maps.
- Retrieve, rank, compress, and pack task-specific context under hard token budgets.
- Redact secrets and enforce provider, egress, prompt-injection, cache, memory, and trace policy.
- Manage local memory through a redacted context repository, progressive disclosure, pinned memory,
  temporal facts, context DAG references, novelty gates, and garbage collection scaffolds.
- Assemble cache-friendly prompts and persist local JSON traces with selected and omitted context.
- Plan controlled harness turns before execution, including token-threshold compaction, turn limits,
  and tool permission preflight.
- Expose provider-neutral LLM, embedding, cache, memory, tool, workflow, and evaluation interfaces.

## Package Boundaries

- `packages/opencontext_core`: pure runtime domain logic. It must not import FastAPI, CLI
  frameworks, provider SDKs, stack frameworks, or storage-specific services.
- `packages/opencontext_api`: thin FastAPI adapter over core runtime APIs.
- `packages/opencontext_cli`: command-line adapter over core runtime APIs.
- `packages/opencontext_profiles`: first-party technology profile hints above core.

## Implemented Runtime Flow

1. `OpenContextRuntime.setup_project()` creates local project harness files and indexes the project.
2. The indexer persists a project manifest, dependency graph, symbols, and repo-map material.
3. Retrieval selects task-relevant candidates from the manifest and optional linked project tunnels.
4. Ranking and context packing enforce priority, source trust, token density, and hard budgets.
5. Safety layers redact and classify content before prompt assembly, memory, traces, cache, or export.
6. Prompt assembly produces stable/cacheable sections and untrusted retrieved evidence.
7. The LLM gateway route is provider-neutral; default tests use `mock/mock-llm`.
8. Local traces record selected context, omitted context, token estimates, prompt sections, and timing.

## Safety Defaults

Core fails closed: external providers, native tools, MCP execution, network egress, raw trace storage,
semantic cache, and automatic memory harvesting are disabled unless explicitly enabled by policy.
