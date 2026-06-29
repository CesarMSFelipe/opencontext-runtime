# OpenContext Public Contracts & API Specification
## Version 1.0 (Draft)
### Document ID
OC-CONTRACTS-001

# Purpose

This document defines the stable public contracts exposed by OpenContext.

Everything outside Runtime Core communicates through versioned contracts.

## Public Contract Families

- WorkflowDefinition
- WorkflowRun
- RuntimeSession
- RuntimeEvent
- Artifact
- Receipt
- PersonaDefinition
- SkillDefinition
- HarnessDefinition
- PolicyDecision
- ContextEnvelope
- MemoryRecord
- Knowledge Graph
- Plugin Manifest
- Provider APIs

## Versioning

Every public schema includes:

- schema_version
- compatibility_version
- deprecated_since (optional)

Breaking changes are only allowed in major versions.

## Stability Levels

- experimental
- beta
- stable
- deprecated
- removed

## Compatibility Rules

- Runtime Core may evolve internally.
- Public contracts remain stable.
- Plugins depend only on public contracts.
- MCP and CLI consume the same contracts.
- Studio renders the same contracts.

## API Groups

### Runtime API
- start_session
- resume_session
- cancel_session
- workflow_run
- workflow_status

### Workflow API
- list_workflows
- describe_workflow
- validate_workflow

### Persona API
- list_personas
- resolve_persona

### Skill API
- list_skills
- resolve_skill

### Harness API
- list_harnesses
- run_harness

### Memory API
- search
- promote
- supersede

### KG API
- query
- retrieve_subgraph
- apply_delta

### Runtime Intelligence API
- estimate_cost
- estimate_confidence
- simulate
- benchmark
- health

## MCP Alignment

The MCP server should expose these contracts directly instead of bespoke payloads.

## CLI Alignment

CLI output is generated from the same contracts used by MCP.

## Studio Alignment

Studio consumes events, artifacts, receipts and runtime state without private APIs.

## Definition of Done

- Every public API has a versioned schema.
- Plugins compile against contracts only.
- Runtime internals remain replaceable.
- Documentation is generated from schemas.

## Final Statement

Public contracts are the long-term compatibility layer of OpenContext.
