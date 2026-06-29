# OpenContext Configuration & UX Architecture
## Version 1.0 (Draft)
### Document ID
OC-CONFIG-UX-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`
- `02-runtime-architecture.md`

---

# 1. Purpose

This document defines the configuration and user experience architecture for OpenContext.

Configuration must make OpenContext powerful without making the first user experience complex.

The default configuration must be good enough for real work.

Advanced configuration must exist, but it must not be required for first success.

---

# 2. Mission

The configuration system exists to make OpenContext:

- predictable
- safe
- explainable
- profile-driven
- project-aware
- easy to install
- easy to debug
- easy to override

The UX must help the user understand what OpenContext will do, what it did, and why.

---

# 3. Core Principles

1. Defaults must work.
2. Profiles hide complexity.
3. Configuration is centralized.
4. Advanced configuration is progressive.
5. Every automatic choice must be explainable.
6. No hidden magic.
7. Safe defaults beat permissive defaults.
8. Missing capabilities should produce helpful guidance.
9. UX must show artifacts, not just chat.
10. First install must lead to a useful first task.

---

# 4. Primary Configuration File

The primary configuration file is:

```text
opencontext.yaml
```

It must be human-readable, versioned and stable.

---

# 5. Configuration Areas

```yaml
version: 2

profile: balanced

workflow: {}
runtime: {}
context: {}
kg: {}
memory: {}
compression: {}
personas: {}
skills: {}
harnesses: {}
policies: {}
capabilities: {}
providers: {}
observability: {}
runtime_intelligence: {}
plugins: {}
studio: {}
```

---

# 6. Profiles

Profiles provide good defaults.

Built-in profiles:

- balanced
- low-cost
- enterprise
- research
- performance

## balanced

Default profile.

Optimized for first-run success.

## low-cost

Minimizes token and provider usage.

## enterprise

Prioritizes safety, approval, observability and auditability.

## research

Prioritizes rich artifacts and deeper context.

## performance

Prioritizes local-first execution and low latency.

---

# 7. Default Balanced Config

```yaml
version: 2
profile: balanced

workflow:
  default: auto
  available:
    - sdd
    - oc-flow

runtime:
  mode: run_to_completion
  resume: true
  checkpoints: true
  live_state: true

context:
  strategy: surgical_first
  max_tokens:
    oc_flow: 6500
    sdd: 18000

kg:
  enabled: true
  mode: balanced
  incremental: true

memory:
  enabled: true
  project_memory: true
  failure_patterns: true
  promotion_policy: evidence_based

compression:
  enabled: true
  semantic_gc: true

harnesses:
  context: strict
  mutation: strict
  inspection: strict
  diagnosis: workflow_default
  review: workflow_default
  security: conditional

policies:
  preset: balanced
  auto_apply: ask_if_risky
  network: deny_by_default
  secrets: redact

runtime_intelligence:
  cost: true
  confidence: true
  simulation: true

observability:
  events: jsonl
  live_state: true
```

---

# 8. Configuration Resolution Order

Configuration is resolved in this order:

1. Built-in defaults
2. Profile defaults
3. Global user config
4. Project config
5. Environment variables
6. CLI/MCP request overrides
7. Runtime policy decisions

Every resolved run must persist a config snapshot.

---

# 9. Config Snapshot

Every session stores:

```text
.opencontext/sessions/<session_id>/config-snapshot.yaml
```

This makes executions reproducible.

---

# 10. UX Modes

Supported UX modes:

- simple
- standard
- advanced
- studio

## simple

Minimal output.

## standard

Default.

Shows workflow, status, artifacts and next action.

## advanced

Shows gates, receipts, cost, confidence and events.

## studio

Visual UI.

---

# 11. CLI UX

Required commands:

```bash
opencontext init
opencontext doctor
opencontext index
opencontext run "task"
opencontext workflow list
opencontext workflow explain oc-flow
opencontext profile list
opencontext profile explain balanced
opencontext session list
opencontext session status <id>
opencontext session resume <id>
opencontext config doctor
```

---

# 12. First Install UX

Expected flow:

```bash
opencontext init
```

Should:

- detect project type;
- suggest profile;
- detect capabilities;
- create opencontext.yaml;
- suggest index;
- explain default workflow behavior.

It should ask as few questions as possible.

---

# 13. Doctor UX

```bash
opencontext doctor
```

Should report:

- detected languages;
- test runners;
- linters;
- KG status;
- memory status;
- provider status;
- missing capabilities;
- recommended next steps.

---

# 14. Run UX

```bash
opencontext run "Fix failing test"
```

Default output should include:

- selected workflow;
- why it was selected;
- current status;
- changed files;
- verification result;
- artifacts;
- next recommended action.

---

# 15. Workflow Explain UX

```bash
opencontext workflow explain sdd
opencontext workflow explain oc-flow
```

Should explain:

- when to use;
- when not to use;
- expected cost;
- outputs;
- phases/nodes;
- harnesses.

---

# 16. Profile Explain UX

```bash
opencontext profile explain enterprise
```

Should explain:

- workflow defaults;
- security mode;
- token budget;
- approval rules;
- inspection strictness;
- observability.

---

# 17. MCP UX

MCP responses must be concise but useful.

`opencontext_run` should return:

- session_id
- run_id
- workflow
- status
- summary
- artifacts
- gates
- next_recommended

Not just counts.

---

# 18. Studio UX

Studio is the visual control plane.

It should show:

- workflow graph;
- live node;
- events;
- context envelope;
- memory used;
- KG subgraph;
- skills/personas/harnesses;
- artifacts;
- receipts;
- cost;
- confidence;
- benchmark trends;
- runtime health.

---

# 19. Error UX

Errors must be actionable.

Bad:

```text
Verification failed.
```

Good:

```text
Verification failed because pytest is not available.
Configure inspection.tests.command or install pytest.
```

Every error should include:

- what failed;
- why it failed;
- whether recoverable;
- what to do next;
- artifact path if available.

---

# 20. Progressive Disclosure

Users should not see advanced internals unless needed.

Default output:

```text
Workflow selected: oc-flow
Status: completed
Verified: tests passed
Artifacts: patch.diff, summary.md
```

Advanced output:

```text
Gates: 12 passed, 1 warning
Cost: 5,820 tokens
Confidence: 0.87
Receipts: 6
```

---

# 21. Configuration Validation

`opencontext config doctor` validates:

- schema version;
- unknown keys;
- invalid profile;
- broken provider config;
- missing commands;
- invalid workflow IDs;
- invalid persona/skill/harness references;
- unsafe policy combinations.

---

# 22. Environment Variables

Environment variables may override:

- provider secrets;
- runtime mode;
- profile;
- telemetry endpoint;
- local cache paths.

They must not silently override safety policies unless explicit.

---

# 23. Policy UX

When a policy blocks execution, user sees:

```text
Policy blocked file write.

Policy: forbidden_paths
Path: .env
Reason: secrets file is protected.
Next: choose another path or request explicit approval.
```

---

# 24. Configuration Invariants

1. Defaults work.
2. Profiles are documented.
3. Every run persists config snapshot.
4. Unknown config keys warn.
5. Unsafe config requires explicit opt-in.
6. CLI/MCP overrides are recorded.
7. UX explains automatic choices.
8. First run requires minimal setup.
9. Config schema is versioned.
10. Studio reads the same config as CLI/MCP.

---

# 25. Definition of Done

Implemented when:

- opencontext.yaml schema exists.
- profiles exist.
- init creates usable config.
- doctor works.
- run output is useful.
- workflow explain works.
- profile explain works.
- config doctor works.
- MCP output is improved.
- Studio reads config.
- every run stores config snapshot.

---

# 26. Final Statement

Configuration should not expose complexity.

It should encode judgement.

A good OpenContext configuration makes the right thing the easiest thing.
