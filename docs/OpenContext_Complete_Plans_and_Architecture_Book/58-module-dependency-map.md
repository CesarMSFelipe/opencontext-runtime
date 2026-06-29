# 58 — Module Dependency Map

Authority: architecture review §2 (imprescindible #2). Prevents circular dependencies as the
Runtime vNext grows to tens of thousands of lines. Every PR MUST keep imports pointing **downward
only** in this layering. Enforced by a guard (see Enforcement).

## Layering (dependencies point down only)

```
L0  Contracts / Models / IDs            (models/, contracts, global IDs — doc 59)
      ▲ no imports from any higher layer
L1  Runtime Core                         runtime/  (EventBus, Session, Run, StateMachine,
                                          WorkflowRunner, RuntimeApi)
L2  Stores & Evidence                    ArtifactStore, ReceiptStore, RunManifest, Checkpoint,
                                          DecisionLog
L3  Governance                           Policy, Capability Graph, Profiles
L4  Knowledge substrate                  KG ─ Memory ─ Cache ─ Compression
L5  Context Engine                       ContextEngine (ranks+assembles over L4) → ContextEnvelope
L6  Registries                           Persona / Skill / Harness / Workflow registries
L7  Providers                            ProviderGateway (over L3 policy)
L8  Orchestration                        Runtime Brain + Scheduler (advisory; governs nothing)
L9  Workflows                            SDD, OC Flow (compose L1–L8 via contracts)
L10 Runtime Intelligence                 Cost / Confidence / Simulator / Benchmark / Evolution
L11 Interfaces                           CLI / MCP / Studio API / Plugin host
```

Canonical tree (review §2, expanded):

```
Runtime
 ├── EventBus
 ├── Session
 ├── Run
 ├── Stores (Artifact/Receipt/Checkpoint/DecisionLog)
 ├── Scheduler ──────────► (advisory only; reads Intelligence, writes Decisions)
 ├── WorkflowRegistry
 ├── ContextEngine
 │      ├── KG
 │      ├── Memory
 │      ├── Cache
 │      ├── Compression
 │      └── Ranking            (NEW — review §9; rank after retrieve)
 ├── ProviderGateway
 ├── Policy
 ├── Runtime Intelligence
 └── Studio API
```

## Allowed / forbidden edges

- **Allowed:** any module imports from a strictly lower layer only.
- **Forbidden:** upward imports; sibling cycles within a layer (e.g. KG↔Memory must not import
  each other — they meet in L5 ContextEngine).
- **Cache (L4)** is a leaf utility: it may be *called* by KG/Memory/Context/Provider but must not
  import them (it takes keys + producers, returns values). Avoids the classic cache cycle.
- **Runtime Brain/Scheduler (L8)** read Intelligence (L10) only through an injected port, not a
  direct import, to avoid L8↔L10 cycle. Intelligence is the lower contract; the port lives in L0.
- **Workflows (L9)** never import each other; SDD and OC Flow share only L1–L8 (book §9.2).

## Per-PR ownership

L1→PR-001; L2→PR-002; L3→PR-005/PR-000.2; L4→PR-008/009/000.3/010(compression); L5→PR-010
(+Ranking review §9); L6→PR-003/006; L7→PR-012; L8→PR-000.1; L9→PR-004/007; L10→PR-011;
L11→PR-013/014/015. Migration across layers is governed by `pr-000-0-compatibility-layer`.

## Enforcement

Add an import-contract guard so a violation fails CI (release gate, PR-017):
- Prefer `import-linter` (`importlinter` contracts: one `layers` contract over the L0–L11 list).
- Fallback (zero new dep): a `tests/architecture/test_no_upward_imports.py` that walks
  `packages/opencontext_core/opencontext_core/`, parses imports with `ast`, and asserts no module
  in layer N imports a module declared in layer >N (layer membership from a small dict).

ponytail: start with the `ast` test (stdlib, no new dep). Promote to import-linter only if the
dict map becomes unwieldy.
