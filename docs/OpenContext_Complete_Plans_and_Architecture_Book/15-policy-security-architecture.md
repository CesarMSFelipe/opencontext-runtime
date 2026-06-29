# OpenContext Policy & Security Architecture
## Version 1.0 (Draft)
### Document ID
OC-POLICY-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`
- `02-runtime-architecture.md`
- `07-harness-architecture.md`
- `13-configuration-ux-architecture.md`

---

# 1. Purpose

This document defines the Policy and Security Architecture for OpenContext.

Policies are runtime-enforced rules that govern what OpenContext may read, write, execute, call, remember, expose or automate.

Policies are not prompts.

Policies are not recommendations.

Policies are executable governance.

---

# 2. Mission

The Policy Engine exists to ensure OpenContext can operate safely in real software repositories.

It must protect:

- source code
- credentials
- production systems
- user data
- private context
- third-party services
- runtime integrity
- project conventions
- organizational boundaries

The runtime must be safe by default.

---

# 3. Core Principles

1. Policies are enforced by the Runtime, not the model.
2. Unsafe operations require explicit permission.
3. Security-sensitive operations are recognized before execution.
4. Every policy decision is logged.
5. Denials must be actionable.
6. Policy violations are never silently ignored.
7. Secrets are redacted before provider calls.
8. Plugins are permissioned.
9. Auto-apply is constrained by risk.
10. Safety overrides speed.

---

# 4. Policy Engine Position

```text
Runtime
  -> Policy Engine
    -> Policy Set
      -> Policy Decision
        -> Allow / Warn / Ask / Deny
```

All mutating or external operations must pass through the Policy Engine.

---

# 5. Governed Operations

Policies govern:

- file reads
- file writes
- file deletes
- command execution
- network calls
- provider calls
- secret access
- memory writes
- KG writes
- plugin loading
- auto-apply
- workflow switching
- escalation
- benchmark execution

---

# 6. PolicyDecision

```python
class PolicyDecision(BaseModel):
    schema_version: str = "opencontext.policy_decision.v1"
    decision_id: str
    operation: str
    decision: Literal["allow", "warn", "ask", "deny"]
    reason: str
    policy_id: str
    evidence_refs: list[str]
    required_approval: bool
    created_at: str
```

Every decision creates an event.

Significant decisions create receipts.

---

# 7. Policy Presets

Built-in presets:

- permissive
- balanced
- restricted
- air_gapped

## balanced

Default.

- deny network by default;
- redact secrets;
- allow low-risk local reads;
- ask for high-risk writes;
- block forbidden paths.

## enterprise

Equivalent to restricted plus audit-oriented defaults.

## air_gapped

No external providers or network access.

---

# 8. Policy DSL

```yaml
policies:
  preset: balanced

  files:
    forbidden_paths:
      - ".env"
      - "secrets/"
      - "*.pem"
      - "node_modules/"
      - "vendor/"

  commands:
    allow:
      - "pytest *"
      - "npm test"
      - "vendor/bin/phpunit *"
    deny:
      - "rm -rf *"
      - "curl * | sh"

  network:
    default: deny

  providers:
    redact_secrets: true

  auto_apply:
    low_risk: allow
    medium_risk: ask
    high_risk: deny
```

---

# 9. File Policy

File policy controls:

- allowed reads;
- allowed writes;
- forbidden paths;
- generated directories;
- protected files;
- large deletions;
- binary files.

Protected by default:

```text
.env
*.pem
*.key
secrets/
credentials/
node_modules/
vendor/
dist/
build/
```

---

# 10. Command Policy

Commands are classified before execution.

Categories:

- safe read-only
- test/lint/typecheck
- package manager
- destructive
- network
- unknown

Unknown commands default to `ask` or `deny` depending on profile.

---

# 11. Network Policy

Default:

```yaml
network:
  default: deny
```

Network access requires:

- explicit config;
- reason;
- domain allowlist;
- receipt.

---

# 12. Provider Policy

Before provider calls:

- redact secrets;
- minimize context;
- apply data policy;
- record provider call;
- enforce token budget.

Provider calls must not receive raw secret-bearing files.

---

# 13. Secret Policy

Secret detection is mandatory before:

- provider calls;
- memory writes;
- artifact publication;
- plugin publishing;
- external telemetry export.

If secrets are detected:

- redact;
- warn;
- block if strict.

---

# 14. Memory Policy

Memory writes are governed.

Forbidden memory content:

- chain-of-thought
- credentials
- raw private logs
- unverified speculation
- duplicate source code

Memory candidates must pass the Memory Harness.

---

# 15. Plugin Policy

Plugins require permissions.

Plugin manifest must declare:

- filesystem access;
- network access;
- command access;
- provider access;
- KG/memory write access.

Untrusted plugins run restricted.

---

# 16. Auto-Apply Policy

Auto-apply is risk-based.

Low-risk:

- small localized changes;
- tests available;
- no public API;
- no secrets;
- no destructive paths.

Medium-risk:

- multiple files;
- public behaviour;
- test uncertainty.

High-risk:

- auth;
- billing;
- secrets;
- migrations;
- broad refactors;
- deletes;
- network/export.

---

# 17. Approval Flow

When policy returns `ask`, Runtime pauses.

Approval prompt must include:

- operation;
- reason;
- risk;
- affected files;
- evidence;
- alternatives.

Approval is recorded as receipt.

---

# 18. Security Harness Integration

Security Harness consumes Policy Engine output and produces:

- findings
- gates
- receipts
- blocking decisions

Security Harness may escalate if policy risk is high.

---

# 19. Events

Required events:

- policy.evaluated
- policy.allowed
- policy.warned
- policy.ask
- policy.denied
- policy.approved
- policy.violation
- secret.detected
- network.blocked
- command.blocked

---

# 20. Receipts

Receipts are required for:

- denied operations;
- approvals;
- high-risk allows;
- auto-apply;
- provider calls;
- network calls;
- memory writes;
- plugin activation.

---

# 21. Studio UX

Studio should show:

- policy decisions;
- blocked operations;
- approvals;
- secret findings;
- plugin permissions;
- auto-apply risk;
- security events.

---

# 22. Migration from Current Branch

Migration steps:

1. Preserve existing forbidden paths/commands.
2. Introduce PolicyDecision.
3. Route file mutation through Policy Engine.
4. Route command execution through Policy Engine.
5. Add provider redaction.
6. Add approval receipts.
7. Integrate with MCP output.
8. Add Studio policy view.

---

# 23. Invariants

1. Policy is runtime-enforced.
2. Prompts cannot override policy.
3. Mutations require policy evaluation.
4. Commands require policy evaluation.
5. Provider calls require redaction.
6. Secrets are never persisted.
7. Approvals are recorded.
8. Plugin permissions are explicit.
9. Denials are actionable.
10. Security beats speed.

---

# 24. Definition of Done

Policy Architecture is implemented when:

- Policy Engine exists.
- PolicyDecision exists.
- File operations are governed.
- Commands are governed.
- Provider calls are redacted.
- Secrets are scanned.
- Auto-apply policy works.
- Approval flow works.
- Policy events and receipts exist.
- Plugins are permissioned.

---

# 25. Final Statement

Policies are the guardrails of OpenContext.

A runtime that can write code must first know when it must not.
