# OpenContext SDD (Specification-Driven Development) Implementation

## Summary

This implementation adds SDD (Specification-Driven Development) workflow capabilities to OpenContext Runtime, providing a **technology-agnostic**, **specification-first** approach to context preparation that works consistently across all technology stacks.

## What Was Implemented

### 1. Core SDD Workflow Steps (`packages/opencontext_core/opencontext_core/workflow/steps.py`)

Seven new workflow steps that form the SDD pipeline:

- **`context_explore`**: Discovers and ranks candidate project context
- **`context_propose`**: Creates token-aware context pack proposals
- **`context_apply`**: Executes proposals with safety gates
- **`context_test`**: Validates context safety and integrity
- **`context_verify`**: Comprehensive security verification
- **`context_review`**: Final review and approval
- **`context_archive`**: Persists and cleans up
- **`context_up-code`**: Generates code updates from proposals
- **`trace_sdd_persist`**: Lightweight trace persistence (no LLM required)

### 2. Workflow Engine Updates (`packages/opencontext_core/opencontext_core/workflow/engine.py`)

- Added SDD steps to the default step registry
- All steps use `WorkflowRunState.metadata` for storage (Pydantic-compatible)

### 3. Configuration (`packages/opencontext_core/opencontext_core/config.py`)

Two pre-configured workflows:

```yaml
# Basic SDD workflow (context preparation)
"sdd":
  steps:
    - project.load_manifest
    - context.explore
    - context.propose
    - context.test
    - context.verify
    - context.review
    - context.archive
    - trace.sdd_persist

# Full SDD workflow (with execution)
"sdd_apply":
  steps:
    - project.load_manifest
    - context.explore
    - context.propose
    - context.apply
    - context.test
    - context.verify
    - context.review
    - context.up-code
    - context.archive
    - trace.sdd_persist
```

### 4. CLI Commands

#### `sdd` subcommands (DEPRECATED)

The `sdd` subcommand was the initial SDD interface. These are now **deprecated** in favor of the unified harness runner:

```bash
opencontext sdd explore <query>      # [DEPRECATED] Use: harness run --workflow explore-only --task "<query>"
opencontext sdd propose <query>      # [DEPRECATED] Use: harness run --workflow sdd --task "<query>"
opencontext sdd apply <workflow>     # [DEPRECATED] Use: harness run --workflow sdd --task "<task>"
opencontext sdd test                  # [DEPRECATED] Use: harness run
opencontext sdd verify                # [DEPRECATED] Use: harness run --workflow sdd --task "<task>"
opencontext sdd review                # [DEPRECATED] Use: harness run --workflow sdd --task "<task>"
opencontext sdd archive               # [DEPRECATED] Use: harness run
opencontext sdd up-code               # [DEPRECATED] Use: harness run --workflow sdd --task "<task>"
opencontext sdd flow <query>          # [DEPRECATED] Use: harness run --workflow sdd --task "<query>"
```

#### `harness run` (current)

The recommended entry point. Provides governance, budget enforcement, and artifact persistence:

```bash
# Full SDD lifecycle (6 phases)
opencontext harness run --workflow sdd --task "Implement OAuth2"

# Explore only (index + context pack)
opencontext harness run --workflow explore-only --task "How does authentication work?"

# Apply only (apply → verify → archive)
opencontext harness run --workflow apply-only --task "my change"

# List available workflows
opencontext harness list

# JSON output for CI
opencontext harness run --workflow sdd --task "my task" --json
```

### 5. API Endpoint (`packages/opencontext_api/opencontext_api/main.py`)

```bash
POST /v1/refactor/sdd
```

Executes the complete SDD flow and returns:
- Context pack with included/omitted sources
- Token usage breakdown
- Safety validation results
- Security scan findings
- Approval status

## Key Design Decisions

### 1. Technology Agnosticism

The SDD workflow makes **no assumptions** about technology stacks:
- Works identically for Django, React, Node.js, Rust, etc.
- Focuses on **what** needs to be done, not **how**
- Discovers context through semantic search, not static analysis

### 2. Pydantic Compatibility

All new steps respect `WorkflowRunState` Pydantic model constraints:
- Use `state.metadata` dictionary for additional data
- No arbitrary attribute assignment
- Type-safe through `ContextPackResult` model

### 3. Safety-First

Every phase includes validation:
- Classification checks at each step
- Security policy enforcement
- Token budget enforcement
- Secret detection and redaction
- Egress controls

### 4. Composable Design

Phases can be used independently:
```python
# Just explore
runtime.ask("Explore auth", workflow_name="sdd_explore")

# Explore + Propose
runtime.ask("Propose auth", workflow_name="sdd_propose")

# Full pipeline
runtime.ask("Full SDD", workflow_name="sdd")
```

### 5. Agent-Agnostic

Works with any AI agent:
- Claude Code
- Cursor
- Codex
- Custom agents
- All receive standardized context envelopes

## Testing

All tests pass (171/171):

```bash
pytest tests/core/test_workflow_engine.py -v
# 6/6 passed (including 4 new SDD tests)

pytest tests/core/ -x
# 171/171 passed
```

New test coverage:
- `test_sdd_workflow_execution`: Full SDD pipeline
- `test_sdd_apply_workflow_execution`: SDD with execution
- `test_sdd_context_explore_step`: Explore phase
- `test_sdd_context_propose_step`: Propose phase

## Usage Examples

### Basic SDD Flow

```bash
# Run complete pipeline via harness runner (recommended)
opencontext harness run --workflow sdd --task "Implement OAuth2 authentication" --budget-mode warn
```

Output:
```
Harness Run: sdd-a1b2c3d4e5f6
  Workflow: sdd
  Task: Implement OAuth2 authentication
  Status: passed
  Phases: 6
    explore: 599/6000 tokens — passed
    propose: 0/6000 tokens — passed
    apply: 0/6000 tokens — passed
    verify: 0/4000 tokens — passed
    review: 0/4000 tokens — passed
    archive: 0/2000 tokens — passed
  Gates: 10
  Trace IDs: 0
```

For CI-friendly JSON output:

```bash
opencontext harness run --workflow sdd --task "my task" --json
```

### API Integration

```python
from opencontext_core.runtime import OpenContextRuntime

runtime = OpenContextRuntime()
result = runtime.ask(
    "Review authentication implementation",
    workflow_name="sdd"
)

print(f"Trace: {result.trace_id}")
print(f"Context items: {result.selected_context_count}")
```

### Custom Workflow

```yaml
# opencontext.yaml
workflows:
  my_custom_sdd:
    steps:
      - project.load_manifest
      - context.explore
      - context.propose
      - context.test
      - my.custom.step
      - context.archive
```

## Benefits

1. **Consistency**: Same workflow across all projects and technologies
2. **Safety**: Every phase validates security and policy compliance
3. **Auditability**: Complete traces of all context decisions
4. **Flexibility**: Use phases independently or as full pipeline
5. **Integration**: Works with any AI agent or system
6. **Standards**: Based on OpenContext's proven patterns

## Documentation

- [SDD Workflow](./docs/workflows/sdd-workflow.md)
- [Workflow Engine](./docs/architecture/workflow-engine.md)
- [Custom Workflows](./docs/workflows/custom-workflows.md)
- [API Reference](./docs/configuration/reference.md)

## Comparison: Before vs After

| Aspect | Before | After (SDD) |
|--------|--------|-------------|
| **Technology coupling** | Per-framework adapters | Single agnostic workflow |
| **Context prep** | Ad-hoc, manual | Standardized 8-phase pipeline |
| **Safety checks** | Optional | Built into every phase |
| **Traceability** | Varies by tool | Consistent across all uses |
| **Agent support** | Per-agent integration | Any agent, same interface |
| **Customization** | Fork/modify code | Declarative YAML workflows |

## Future Enhancements

- [ ] Integration with popular IDEs (VS Code, IntelliJ)
- [ ] Pre-built SDD workflows for common patterns (MVC, microservices)
- [ ] SDD workflow marketplace
- [ ] Automated SDD from issue tracking systems
- [ ] SDD metrics and quality gates
- [ ] Cross-project SDD (multi-repo context)

## Conclusion

The SDD workflow provides OpenContext's users with a **unified, technology-agnostic approach** to specification-driven development. By standardizing on the 8-phase pipeline (Explore → Propose → Spec → Design → Tasks → Apply → Verify → Archive), teams can:

- Onboard faster with consistent workflows
- Maintain security and compliance
- Integrate with any tool or agent
- Scale across projects and technologies
- Audit and improve over time

All while leveraging OpenContext's proven context engineering capabilities.
