# OpenContext PR-001 Runtime Core Implementation Specification
## Version 1.0 (Draft)
### Document ID
OC-PR-001-RUNTIME-CORE

# Purpose

This document defines the first implementation PR for the OpenContext architecture roadmap.

PR-001 introduces the Runtime Core foundation while preserving the existing `opencontext_run` behaviour.

---

# Scope

PR-001 adds:

- RuntimeSession
- RuntimeRun
- SessionStore
- RuntimeEvent
- EventBus
- LiveState
- minimal RuntimeApi façade
- compatibility wrapper around existing HarnessRunner

PR-001 does not add:

- OC Flow
- Workflow Registry
- new KG
- new Memory
- Plugin SDK
- Studio

---

# Architecture References

- `02-runtime-architecture.md`
- `14-observability-benchmark-architecture.md`
- `24-artifact-receipt-lifecycle.md`
- `49-pr-sequencing-plan.md`

---

# Goals

1. Every execution has a session.
2. Every execution has a run.
3. Every run emits events.
4. Live state is persisted.
5. Existing MCP usage still works.
6. Existing SDD flow is not broken.

---

# Non-Goals

- Refactor all workflows.
- Replace HarnessRunner.
- Introduce new workflow definitions.
- Change user-facing behaviour significantly.

---

# Proposed Files

```text
opencontext_core/runtime/
  __init__.py
  api.py
  session.py
  session_store.py
  run.py
  events.py
  event_bus.py
  live_state.py
  errors.py
```

---

# RuntimeSession

```python
class RuntimeSession(BaseModel):
    schema_version: str = "opencontext.session.v1"
    session_id: str
    root: str
    task: str
    profile: str
    status: str
    active_run_id: str | None
    created_at: str
    updated_at: str
    live_state_path: str
    events_path: str
    artifacts_root: str
```

---

# RuntimeRun

```python
class RuntimeRun(BaseModel):
    schema_version: str = "opencontext.run.v1"
    run_id: str
    session_id: str
    workflow_id: str
    status: str
    started_at: str
    completed_at: str | None
    current_node: str | None
```

---

# RuntimeEvent

```python
class RuntimeEvent(BaseModel):
    schema_version: str = "opencontext.runtime_event.v1"
    event_id: str
    session_id: str
    run_id: str | None
    workflow_id: str | None
    node_id: str | None
    type: str
    status: str
    message: str
    metadata: dict[str, Any]
    created_at: str
```

---

# Session Layout

```text
.opencontext/sessions/<session_id>/
  session.json
  live-state.json
  events.jsonl
  runs/<run_id>/
    run.json
```

---

# Compatibility Strategy

Current `opencontext_run` should continue to call the existing HarnessRunner, but PR-001 wraps execution with:

1. create session;
2. create run;
3. emit started event;
4. call HarnessRunner;
5. emit completed/failed event;
6. persist live state.

---

# Required Events

- session.created
- run.created
- workflow.started
- workflow.completed
- workflow.failed
- live_state.updated

---

# Tests

Required tests:

- creates session folder;
- writes session.json;
- writes run.json;
- writes events.jsonl;
- updates live-state.json;
- preserves legacy HarnessRunner result;
- handles failure and records failed event.

---

# Acceptance Criteria

PR-001 is complete when:

- existing SDD run still works;
- session metadata is persisted;
- run metadata is persisted;
- events are persisted;
- live state is persisted;
- no workflow behaviour changes are introduced.

---

# Rollback Plan

If PR-001 causes instability, compatibility wrapper can be disabled via config:

```yaml
runtime:
  session_wrapper: false
```

---

# Final Statement

PR-001 does not make OpenContext more agentic.

It makes OpenContext more governable.
