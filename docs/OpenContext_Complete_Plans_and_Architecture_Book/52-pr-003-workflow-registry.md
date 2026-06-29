# OpenContext PR-003 Workflow Registry Implementation Specification
## Version 1.0 (Draft)
### Document ID
OC-PR-003-WORKFLOW-REGISTRY

# Purpose

This document specifies PR-003 for OpenContext.

PR-003 introduces the Workflow Registry and declarative WorkflowDefinition model while preserving the current SDD execution path.

The objective is to stop treating workflows as hardcoded runner modes and start treating them as versioned runtime contracts.

---

# Scope

PR-003 adds:

- WorkflowDefinition
- WorkflowNodeDefinition
- WorkflowEdgeDefinition
- WorkflowRegistry
- WorkflowResolver
- Built-in SDD workflow definition
- Compatibility aliases for existing workflow names
- Workflow validation

PR-003 does not add:

- OC Flow
- Runtime Intelligence
- new KG/Memory
- Plugin workflow loading

---

# Architecture References

- `01-system-architecture.md`
- `02-runtime-architecture.md`
- `03-sdd-workflow-architecture.md`
- `17-public-contracts-api-specification.md`
- `49-pr-sequencing-plan.md`

---

# Goals

1. Workflows become declarative.
2. SDD is registered as a built-in workflow.
3. Existing `full`, `standard`, `quick` workflow aliases still work.
4. Runtime can resolve workflow IDs consistently.
5. Invalid workflow definitions fail validation early.
6. Future OC Flow can be added without changing Runtime Core.

---

# Proposed Files

```text
opencontext_core/workflows/
  __init__.py
  definition.py
  registry.py
  resolver.py
  validation.py
  aliases.py
  builtins/
    sdd.yaml
```

---

# WorkflowDefinition

```python
class WorkflowDefinition(BaseModel):
    schema_version: str = "opencontext.workflow.v1"
    id: str
    version: str
    label: str
    kind: str
    description: str
    start_node: str
    terminal_nodes: list[str]
    nodes: dict[str, WorkflowNodeDefinition]
    edges: list[WorkflowEdgeDefinition]
    default_profile: str | None = None
    metadata: dict[str, Any] = {}
```

---

# WorkflowNodeDefinition

```python
class WorkflowNodeDefinition(BaseModel):
    id: str
    label: str
    role: str
    action: str
    required_personas: list[str] = []
    required_skills: list[str] = []
    required_harnesses: list[str] = []
    required_outputs: list[str] = []
    gates: list[str] = []
    retry_policy: dict[str, Any] = {}
```

---

# WorkflowEdgeDefinition

```python
class WorkflowEdgeDefinition(BaseModel):
    from_node: str
    to_node: str
    condition: str | None = None
```

---

# Built-in SDD Workflow

The first built-in workflow definition should model the existing SDD flow.

Canonical nodes:

```text
explore
propose
spec
design
tasks
apply
verify
review
archive
```

Legacy variants may map to profiles or aliases, not separate hardcoded runner branches.

---

# Compatibility Aliases

Existing workflow names must continue working.

```python
WORKFLOW_ALIASES = {
    "full": "sdd",
    "standard": "sdd",
    "quick": "sdd",
    "sdd": "sdd",
}
```

Profile mapping:

```text
full      -> sdd/full profile
standard  -> sdd/standard profile
quick     -> sdd/quick profile
```

---

# WorkflowRegistry

```python
class WorkflowRegistry:
    def register(self, definition: WorkflowDefinition) -> None: ...
    def get(self, workflow_id: str) -> WorkflowDefinition: ...
    def list(self) -> list[WorkflowDefinition]: ...
    def resolve_alias(self, workflow: str) -> str: ...
```

---

# Workflow Validation

Validation checks:

- schema version exists;
- workflow ID exists;
- start node exists;
- terminal nodes exist;
- all edges reference valid nodes;
- no unreachable nodes unless explicitly allowed;
- no duplicate node IDs;
- required roles are strings;
- required harness/skill references are valid if registries available.

---

# Runtime Integration

The Runtime should resolve workflow definition before execution.

Current execution may still delegate to the existing HarnessRunner.

PR-003 should not require fully generic WorkflowRunner behaviour yet.

Minimal integration:

```text
opencontext_run
  -> RuntimeApi
    -> WorkflowResolver
      -> existing HarnessRunner
```

---

# Events

PR-003 should emit:

- workflow.resolved
- workflow.alias_resolved
- workflow.validation.passed
- workflow.validation.failed

---

# Receipts

Workflow selection should create or extend:

- workflow-selection receipt

Fields:

- requested workflow
- resolved workflow
- profile
- reason
- compatibility alias if used

---

# Tests

Required tests:

- loads built-in SDD workflow;
- validates SDD workflow graph;
- resolves `sdd`;
- resolves legacy `full`;
- resolves legacy `standard`;
- resolves legacy `quick`;
- rejects unknown workflow;
- rejects invalid workflow definition;
- workflow selection receipt includes alias metadata.

---

# Acceptance Criteria

PR-003 is complete when:

- WorkflowRegistry exists;
- SDD definition exists;
- legacy workflow names still work;
- workflow validation works;
- Runtime records resolved workflow;
- future OC Flow can be registered without Runtime Core changes.

---

# Rollback Strategy

If workflow registry causes instability, compatibility flag:

```yaml
workflow:
  registry_enabled: false
```

When disabled, Runtime uses legacy workflow resolution.

---

# Final Statement

PR-003 is the bridge from hardcoded execution modes to declarative engineering workflows.

It prepares the Runtime for OC Flow without disturbing existing SDD users.
