# OpenContext Organization Graph & Team Topology Architecture
## Version 1.0 (Draft)
### Document ID
OC-ORG-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`
- `08-knowledge-graph-architecture.md`
- `09-memory-architecture.md`
- `15-policy-security-architecture.md`

---

# 1. Purpose

This document defines the Organization Graph and Team Topology Architecture for OpenContext.

The Organization Graph extends OpenContext beyond code structure. It represents teams, owners, services, systems, repositories, runbooks, incidents, policies and responsibility boundaries.

Its purpose is to make runtime decisions aware of human and organizational context.

---

# 2. Mission

The Organization Graph helps OpenContext answer:

- Who owns this code?
- Which team should review this change?
- Which service is affected?
- Is this area high risk?
- Has this service had related incidents?
- Which runbook applies?
- Should this task use SDD instead of OC Flow?
- Who should receive an escalation handoff?
- Which policy applies to this component?

---

# 3. Core Principles

1. Code has owners.
2. Services have operational context.
3. Risk depends on organizational topology.
4. Escalation should be intelligent.
5. Ownership facts require provenance.
6. Unknown ownership must be explicit.
7. Organizational knowledge is temporal.
8. The runtime should not guess owners.
9. Policies may depend on teams/services.
10. Human handoff is a first-class runtime outcome.

---

# 4. Position in Architecture

```text
Knowledge Graph
  -> Organization Graph
      -> Teams
      -> Owners
      -> Services
      -> Systems
      -> Incidents
      -> Runbooks
      -> Policies
```

Used by:

- Workflow Selector
- Escalation Harness
- Security Harness
- Policy Engine
- Runtime Intelligence
- Studio
- Memory
- KG retrieval

---

# 5. Node Types

```python
class OrgNodeType(StrEnum):
    PERSON = "person"
    TEAM = "team"
    SERVICE = "service"
    SYSTEM = "system"
    REPOSITORY = "repository"
    PACKAGE = "package"
    COMPONENT = "component"
    RUNBOOK = "runbook"
    INCIDENT = "incident"
    POLICY = "policy"
    CHANNEL = "channel"
    ONCALL_ROTATION = "oncall_rotation"
    SLA = "sla"
    SLO = "slo"
```

---

# 6. Edge Types

```python
class OrgEdgeType(StrEnum):
    OWNS = "owns"
    MAINTAINS = "maintains"
    OPERATES = "operates"
    REVIEWS = "reviews"
    ESCALATES_TO = "escalates_to"
    DOCUMENTED_BY = "documented_by"
    AFFECTED_BY = "affected_by"
    DEPENDS_ON = "depends_on"
    GOVERNED_BY = "governed_by"
    ALERTS_TO = "alerts_to"
```

---

# 7. Ownership Sources

OpenContext should resolve ownership from multiple sources:

- CODEOWNERS
- repository config
- OpenContext project config
- Git history
- package metadata
- service catalog
- team config
- memory
- manual user input
- plugin providers

Source priority must be configurable.

---

# 8. Owner Resolution

```python
class OwnerResolver:
    def resolve_for_files(self, files: list[str]) -> list[OwnerRef]: ...
    def resolve_for_symbols(self, symbols: list[str]) -> list[OwnerRef]: ...
    def resolve_for_service(self, service: str) -> list[OwnerRef]: ...
```

Resolution output must include confidence and provenance.

---

# 9. OwnerRef

```python
class OwnerRef(BaseModel):
    owner_id: str
    owner_type: Literal["person", "team", "unknown"]
    name: str
    contact: str | None
    source: str
    confidence: float
    evidence_refs: list[str]
```

---

# 10. Unknown Ownership

Unknown ownership is not an error to hide.

It must be represented explicitly:

```json
{
  "owner_type": "unknown",
  "reason": "No CODEOWNERS match and no service catalog entry"
}
```

Unknown ownership may trigger:

- warning;
- escalation;
- SDD instead of OC Flow;
- human clarification;
- memory candidate.

---

# 11. Service Criticality

Services may have criticality levels:

```text
low
medium
high
critical
```

Criticality influences:

- workflow selection;
- review requirements;
- security gates;
- auto-apply;
- escalation;
- benchmark expectations.

---

# 12. Risk-Aware Workflow Selection

Workflow selector uses organization signals.

Use SDD when:

- high-criticality service;
- unknown owner;
- incident-prone component;
- public API;
- security policy applies;
- cross-team boundary.

Use OC Flow when:

- localized low-risk component;
- known owner;
- good tests;
- low blast radius.

---

# 13. Escalation Handoff

Escalation report should include:

- owners
- teams
- channels
- affected services
- risk
- failed attempts
- current patch
- blocking error
- next recommended action

---

# 14. Runbooks

Runbooks may be linked to:

- services;
- components;
- failure patterns;
- incidents;
- policies.

The Diagnosis Harness may retrieve runbooks when relevant.

---

# 15. Incidents

Incident history may influence risk.

Example:

```text
Service X had 3 auth-related incidents in 90 days.
Auth changes require SDD and security review.
```

Incident data is optional and plugin-provided.

---

# 16. Policy Integration

Policies may reference organization graph nodes.

Example:

```yaml
policies:
  services:
    payments:
      auto_apply: false
      review: required
      workflow: sdd
```

---

# 17. Studio Integration

Studio should visualize:

- code owners;
- affected teams;
- service map;
- escalation path;
- criticality;
- runbooks;
- policy overlays;
- unknown ownership gaps.

---

# 18. Events

Required events:

- org.owner.resolved
- org.owner.unknown
- org.service.resolved
- org.escalation.targeted
- org.policy.applied
- org.runbook.retrieved

---

# 19. Receipts

Required receipts:

- owner resolution receipt
- service resolution receipt
- escalation target receipt
- org-policy receipt

---

# 20. Configuration

```yaml
organization:
  enabled: true

  ownership:
    sources:
      - CODEOWNERS
      - opencontext
      - git
    unknown_owner_policy: warn

  services:
    catalog: null

  escalation:
    include_owner_candidates: true
    include_channels: true
```

---

# 21. Plugin Providers

Plugins may provide:

- service catalogs;
- team directories;
- incident systems;
- on-call providers;
- ticket systems;
- chat integrations.

Examples:

- GitHub Teams
- Backstage
- OpsLevel
- PagerDuty
- Jira
- Linear
- Slack

All provider data must be permissioned.

---

# 22. Migration from Current Branch

Migration steps:

1. Add OwnerRef model.
2. Add CODEOWNERS parser.
3. Add OwnerResolver.
4. Link owners to KG nodes.
5. Add escalation owner lookup.
6. Add org receipts/events.
7. Add Studio owner view later.
8. Add plugin providers later.

---

# 23. Invariants

1. Ownership requires provenance.
2. Unknown ownership is explicit.
3. Escalation includes owner candidates when possible.
4. High-risk services may alter workflow selection.
5. Organization data is temporal.
6. Plugins cannot expose private org data without permission.
7. Policies may depend on organization graph.
8. Human handoff is a valid runtime outcome.

---

# 24. Definition of Done

Implemented when:

- CODEOWNERS parsing works.
- OwnerResolver exists.
- KG links files/symbols to owners.
- Escalation reports include owners.
- Unknown owners are surfaced.
- Workflow selector uses org risk signals.
- Policy Engine can reference services/owners.
- Studio visualizes ownership.

---

# 25. Final Statement

OpenContext should not treat code as anonymous text.

Software belongs to teams, services and responsibilities.

The Organization Graph makes the runtime aware of that reality.
