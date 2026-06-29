# OpenContext Knowledge Graph Architecture
## Version 1.0 (Draft)
### Document ID
OC-KG-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`
- `02-runtime-architecture.md`
- `07-harness-architecture.md`

---

# 1. Purpose

This document defines the Knowledge Graph Architecture for OpenContext.

The Knowledge Graph (KG) is the structural and temporal knowledge layer of OpenContext. It exists to answer engineering questions without requiring repeated repository exploration or large context prompts.

The KG is not a cache.

The KG is not memory.

The KG is a typed, evidence-backed representation of code, architecture, dependencies, tests, ownership, decisions, sessions and runtime experience.

---

# 2. Mission

The KG exists to reduce token usage, improve correctness and provide evidence for runtime decisions.

It should help answer:

- Which files and symbols are relevant?
- What depends on this symbol?
- Which tests cover this code?
- Who owns this area?
- What changed recently?
- What previous decisions affect this task?
- What failure patterns are associated with this subsystem?
- What context is sufficient for the current workflow node?

---

# 3. Core Principles

1. KG before broad file reads.
2. Source code remains authoritative for implementation.
3. The graph is authoritative for structure.
4. Every inferred fact needs provenance.
5. Temporal facts must support expiry and supersession.
6. Retrieval must be budgeted.
7. The KG must support incremental updates.
8. The KG must be queryable through stable contracts.
9. Plugins may extend graph schema through versioned namespaces.
10. Runtime decisions based on KG must create receipts.

---

# 4. Position in the Architecture

```text
Runtime
  -> Context Harness
    -> KG Query Planner
      -> KG Providers
        -> Code Graph
        -> Test Graph
        -> Ownership Graph
        -> Decision Graph
        -> Runtime Experience Graph
```

The KG serves:

- Context Harness
- Memory Harness
- Workflow Selector
- Runtime Simulator
- Cost Engine
- Confidence Engine
- Escalation Harness
- Studio
- Plugin SDK

---

# 5. Graph Partitions

The KG is logically partitioned.

```text
Code Graph
Test Graph
Ownership Graph
Architecture Graph
Decision Graph
Runtime Experience Graph
Memory Graph
Skill/Harness Graph
```

Partitions may share storage but must remain semantically distinct.

---

# 6. Node Types

```python
class KgNodeType(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"
    PACKAGE = "package"
    MODULE = "module"
    SYMBOL = "symbol"
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    TEST = "test"
    COMMAND = "command"
    CONFIG = "config"
    SERVICE = "service"
    ROUTE = "route"
    PLUGIN = "plugin"
    OWNER = "owner"
    TEAM = "team"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    FAILURE_PATTERN = "failure_pattern"
    SESSION = "session"
    RUN = "run"
    ARTIFACT = "artifact"
    SKILL = "skill"
    PERSONA = "persona"
    HARNESS = "harness"
```

---

# 7. Edge Types

```python
class KgEdgeType(StrEnum):
    CONTAINS = "contains"
    DEFINES = "defines"
    IMPORTS = "imports"
    CALLS = "calls"
    REFERENCES = "references"
    TESTS = "tests"
    COVERS = "covers"
    OWNS = "owns"
    DEPENDS_ON = "depends_on"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    CONFIGURES = "configures"
    CHANGED_BY = "changed_by"
    PRODUCED_BY = "produced_by"
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    FAILED_WITH = "failed_with"
    FIXED_BY = "fixed_by"
    USED_SKILL = "used_skill"
    USED_HARNESS = "used_harness"
```

---

# 8. KG Node Model

```python
class KgNode(BaseModel):
    id: str
    type: KgNodeType
    name: str
    path: str | None
    language: str | None
    properties: dict[str, Any]
    temporal: TemporalMetadata
    evidence: list[EvidenceRef]
```

---

# 9. KG Edge Model

```python
class KgEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    type: KgEdgeType
    properties: dict[str, Any]
    temporal: TemporalMetadata
    evidence: list[EvidenceRef]
```

---

# 10. Temporal Metadata

Temporal metadata is required for facts that may change.

```python
class TemporalMetadata(BaseModel):
    observed_at: str
    valid_from: str | None
    valid_to: str | None
    confidence: float
    superseded_by: str | None
    status: Literal["active", "stale", "superseded", "rejected"]
```

Temporal support is mandatory for:

- ownership;
- decisions;
- commands;
- architecture constraints;
- failure patterns;
- runtime experience.

---

# 11. Evidence References

```python
class EvidenceRef(BaseModel):
    source_type: Literal["file", "run", "commit", "artifact", "memory", "user", "tool"]
    source_id: str
    path: str | None
    line_start: int | None
    line_end: int | None
    run_id: str | None
    confidence: float
```

Every non-structural or inferred graph fact must include evidence.

---

# 12. Indexing Pipeline

```text
Discover Files
↓
Detect Project Type
↓
Parse Sources
↓
Extract Symbols
↓
Extract Imports
↓
Extract Calls
↓
Extract Tests
↓
Extract Config
↓
Extract Owners
↓
Build Graph
↓
Validate Graph
↓
Persist Index
```

---

# 13. Incremental Indexing

OpenContext must support incremental indexing.

Triggers:

- file change;
- post-run consolidation;
- explicit `opencontext index`;
- plugin request;
- stale index detection.

```python
class GraphDelta(BaseModel):
    added_nodes: list[str]
    updated_nodes: list[str]
    deleted_nodes: list[str]
    added_edges: list[str]
    updated_edges: list[str]
    deleted_edges: list[str]
    affected_symbols: list[str]
```

---

# 14. Supported Languages

Initial priorities:

- Python
- TypeScript
- JavaScript
- PHP
- YAML
- JSON
- Markdown

PHP support should include Drupal and Symfony conventions where detectable.

---

# 15. Drupal/Symfony Extraction

For Drupal/Symfony projects, the KG should extract:

- services.yml
- routing.yml
- permissions.yml
- plugin annotations/attributes
- event subscribers
- controllers
- forms
- entity types
- config schema
- hooks
- composer dependencies
- PHPUnit tests
- PHPStan/PHPcs config

This improves context retrieval for PHP/Drupal tasks.

---

# 16. Query Planner

The KG should not expose only raw graph queries.

It should provide task-aware query planning.

```python
class KgQueryPlanner:
    def plan(self, task: str, workflow: str, node: str, budget: ContextBudget) -> KgQueryPlan: ...
```

---

# 17. Retrieval Modes

```text
symbol_first
test_first
owner_first
failure_first
decision_first
architecture_boundary
```

The Context Harness chooses mode based on workflow node and task type.

---

# 18. Subgraph Retrieval

```python
class ContextSubgraph(BaseModel):
    nodes: list[KgNode]
    edges: list[KgEdge]
    evidence: list[EvidenceRef]
    omitted: list[Omission]
    token_estimate: int
    confidence: float
```

Subgraph retrieval must enforce token and node budgets.

---

# 19. KG Confidence

Each retrieval should produce confidence.

Signals:

- exact symbol match;
- matching tests found;
- owners found;
- graph freshness;
- evidence quality;
- missing links;
- stale nodes.

Low confidence can trigger:

- deeper retrieval;
- OC Flow to SDD switch;
- user clarification;
- escalation.

---

# 20. KG Receipts

Every significant KG operation should create a receipt.

Examples:

- index receipt;
- query receipt;
- retrieval receipt;
- graph update receipt;
- owner resolution receipt.

---

# 21. KG Events

Required events:

- kg.index.started
- kg.index.completed
- kg.index.failed
- kg.query.started
- kg.query.completed
- kg.subgraph.created
- kg.delta.created
- kg.node.superseded
- kg.confidence.low

---

# 22. KG Storage

Initial storage may be local.

Recommended layers:

- JSONL for development/debug
- SQLite for local persistence
- optional graph DB provider through plugin

The architecture must not require a specific graph database.

---

# 23. KG Provider Interface

```python
class KnowledgeProvider(Protocol):
    def index(self, root: Path, options: IndexOptions) -> IndexResult: ...
    def query(self, query: KgQuery) -> KgQueryResult: ...
    def retrieve_subgraph(self, plan: KgQueryPlan) -> ContextSubgraph: ...
    def apply_delta(self, delta: GraphDelta) -> None: ...
```

---

# 24. Relationship with Memory

KG and Memory are different.

KG stores relationships and structure.

Memory stores durable knowledge and learned experience.

Memory records may become KG nodes when useful.

KG nodes may support memory retrieval.

Neither replaces the other.

---

# 25. Relationship with Context Engineering

The KG is the primary source for surgical context retrieval.

The Context Harness should use KG before reading files.

---

# 26. Relationship with Studio

Studio should visualize:

- relevant subgraph;
- owners;
- tests;
- affected symbols;
- recent failures;
- decisions;
- runtime experience edges.

---

# 27. Migration from Current Branch

Migration steps:

1. Preserve current indexing/search behaviour.
2. Add KG schema v2.
3. Add evidence refs.
4. Add incremental delta model.
5. Add query planner.
6. Add context subgraph retrieval.
7. Add owner/test extraction.
8. Add KG receipts/events.
9. Integrate with SDD explore.
10. Integrate with OC Flow gather_context.

---

# 28. Invariants

1. KG facts have provenance.
2. Structural graph reflects source code.
3. Source code remains implementation authority.
4. KG retrieval is budgeted.
5. KG confidence is explicit.
6. KG updates are incremental where possible.
7. KG writes produce receipts.
8. KG providers implement stable interfaces.
9. Context retrieval uses KG before broad file reads.
10. Temporal facts can expire or be superseded.

---

# 29. Definition of Done

KG Architecture is implemented when:

- KG schema v2 exists.
- Indexer builds code/test/owner graph.
- Incremental graph deltas work.
- Context Harness retrieves subgraphs.
- SDD uses KG in explore.
- OC Flow uses KG in gather_context.
- KG confidence is reported.
- KG receipts and events are persisted.
- Studio can visualize relevant subgraphs.
- Plugins can provide KG providers.

---

# 30. Final Statement

The Knowledge Graph is how OpenContext knows the repository.

Without it, agents read files.

With it, the runtime reasons over engineering structure.
