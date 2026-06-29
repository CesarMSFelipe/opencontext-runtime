# REMOVE-IN-2.0 — vNext migration removal backlog

This is the 2.0 removal backlog for code made **DEAD**, **DEPRECATED**, or
**LEGACY-SUPERSEDED-BY-vNEXT** by the vNext program (PR-001..017 +
architecture-verification-hardening + vnext-default-migration).

**Nothing here is deleted.** Each item carries a behavior-preserving
`# DEPRECATED(2.0): …` marker at its definition. A `DeprecationWarning` is added
**only** where the code is already dead (no live caller) or already warned — never
on a legacy path that is still the live default for an un-flipped subsystem (those
would spam and break tests). Cross-referenced against
`compat/migration.py` (`MIGRATION_LEDGER`) and `compat/flags.py`.

Paths are relative to `packages/opencontext_core/opencontext_core/`. Line numbers
point at the marker comment (the definition is on the following line).

## Flag-state context (compat/flags.py + config.RuntimeMigrationConfig)

vNext is now the **default** for 6 subsystems; the legacy half of these is reachable
only via rollback (flag off):

| Flag | Default | vNext default? |
|------|---------|----------------|
| `runtime.session_wrapper` | `True` | yes (legacy = off route) |
| `runtime.registry_enabled` | `True` | yes |
| `runtime.persona_registry_enabled` | `True` | yes |
| `runtime.skill_registry_enabled` | `True` | yes |
| `runtime.harness_registry_enabled` | `True` | yes |
| `runtime.oc_flow_enabled` | `True` | yes |
| `runtime.gateway_enabled` | `False` | **no — legacy is live** |
| `runtime.context_engine_enabled` | `False` | **no — legacy is live** |
| `runtime.kg_v2_enabled` | `False` | **no — legacy is live** |
| `runtime.memory_v2_enabled` | `False` | **no — legacy is live** |

"Safe-to-remove-when" below keys off these flags + the ledger removal milestones.

---

## 1. Agent SDK (dead second agent spine)

A standalone agent framework parallel to the live `harness/` + `agents/executor.py`
spine. Zero live callers outside its own package and tests. `BaseAgent` /
`AgentOrchestrator` already emit `DeprecationWarning`; `SDDOrchestrator.__init__`
now does too (added — dead, tests-only). All other items are comment-only because
they are reached only through the already-warning entry points (an import-time
warning on these would fire when the **live** `agents.executor` is imported).

| Item | Path:line | Category | Superseded-by | Safe-to-remove-when |
|------|-----------|----------|---------------|---------------------|
| `BaseAgent` | `agents/base.py:45` | dead + already-deprecated | `opencontext_core.harness` | 2.0 (no live caller) |
| `AgentOrchestrator` (+ `AgentResult`) | `agents/orchestrator.py:34` | dead + already-deprecated | `opencontext_core.harness` | 2.0 (no live caller) |
| `CodeReviewAgent` | `agents/code_review_agent.py:10` | dead | harness | 2.0 |
| `ContextPlannerAgent` | `agents/context_planner_agent.py:14` | dead | harness | 2.0 |
| `MutationAnalystAgent` | `agents/mutation_analyst_agent.py:11` | dead | harness | 2.0 |
| `SecurityAuditAgent` | `agents/security_audit_agent.py:20` | dead | harness | 2.0 |
| `TDDEnforcerAgent` | `agents/tdd_enforcer_agent.py:11` | dead | harness | 2.0 |
| `load_agent_config` / `list_available_agents` | `agents/loader.py:10` | dead | n/a | 2.0 |
| `TokenBudget` (agents copy) | `agents/token_manager.py:7` | dead | `models.context.TokenBudget` | 2.0 |
| `HookEvent` / `HookRegistry` (agents copy) | `agents/hooks.py:20` | dead | `hooks.models` / `operating_model.team` | 2.0 |
| `DEFAULT_HANDLERS` + handlers | `agents/hook_handlers.py:19` | dead | n/a | 2.0 |
| `MemoryManager` (agents copy) | `agents/memory_manager.py:8` | dead | live `memory/` subsystem | 2.0 |
| `AGENT_REGISTRY` | `agents/__init__.py:32` | dead | n/a | 2.0 |
| `SDDOrchestrator` (class only) | `agents/sdd_orchestrator.py:156` | dead (**new DeprecationWarning**) | folded into `HarnessRunner` | 2.0 (tables/functions in module stay live) |

## 2. Workflow resolution / SDD scheduling (legacy-superseded)

`runtime.registry_enabled` is default-on, but these legacy structures remain
reachable via rollback and the `HarnessRunner` still consults `WORKFLOW_TRACKS` as
its DAG declaration. Comment-only (rollback path still live).

| Item | Path:line | Category | Superseded-by | Safe-to-remove-when |
|------|-----------|----------|---------------|---------------------|
| `WORKFLOW_TRACKS` | `agents/sdd_orchestrator.py:61` | legacy-superseded | PR-003 `WorkflowRegistry` / `workflows/builtins` | `registry_enabled` default + legacy DAG scheduler removed (milestone-C) |
| `HarnessRunner._WORKFLOW_TRACK_ALIASES` | `harness/runner.py:450` | legacy-superseded | PR-003 `WorkflowRegistry` | as above (milestone-C) |

## 3. Provider gateway / firewall (legacy-superseded, still the live default)

`runtime.gateway_enabled` is `False` → these ARE the live default. Comment-only.
Note `llm/provider_gateway.py`'s `build_adapter` / `build_provider_gateway` helpers
are **reused** by the vNext `providers/gateway.py` and must stay; only the legacy
`ProviderGateway` class is superseded.

| Item | Path:line | Category | Superseded-by | Safe-to-remove-when |
|------|-----------|----------|---------------|---------------------|
| `BudgetAwareLLMGateway` | `runtime/__init__.py:155` | legacy-superseded | `providers.gateway.ProviderGateway` (PR-012) | `gateway_enabled` default + legacy removed (milestone-E) |
| `SamplingGateway` | `llm/sampling_gateway.py:44` | legacy-superseded | unified `ProviderGateway` (PR-012) | as above (milestone-E) |
| `ProviderGateway` (legacy shim) | `llm/provider_gateway.py:59` | legacy-superseded | `providers.gateway.ProviderGateway` (PR-012) | as above (milestone-E); keep `build_adapter`/`build_provider_gateway` |
| `ContextFirewall` | `safety/firewall.py:48` | legacy-superseded | unified gateway firewall (PR-012) | as above (milestone-E) |

## 4. Retrieval & context packing (legacy-superseded, still the live default)

`runtime.context_engine_enabled` and `runtime.kg_v2_enabled` are `False` → live
default. Comment-only.

| Item | Path:line | Category | Superseded-by | Safe-to-remove-when |
|------|-----------|----------|---------------|---------------------|
| `RetrievalPlanner` | `retrieval/planner.py:354` | legacy-superseded | PR-008 KG v2 + PR-010 `ContextEngine` | `kg_v2_enabled` + `context_engine_enabled` default + legacy removed (milestone-D) |
| `ContextPackBuilder` | `context/packing.py:20` | legacy-superseded | PR-010 `ContextEngine` | `context_engine_enabled` default + legacy removed (milestone-D) |

## 5. Execution spines (two-spine convergence, CL-008)

| Item | Path:line | Category | Superseded-by | Safe-to-remove-when |
|------|-----------|----------|---------------|---------------------|
| `OcNewConductor` | `oc_new/conductor.py:52` | legacy-superseded | `HarnessRunner`->`RuntimeApi` (chosen spine) | resume carry-over parity on HarnessRunner spine (milestone-C). Still the live oc-new CLI driver — comment-only. |

## 6. Adapter layer (already-deprecated — SDK import surface only)

| Item | Path:line | Category | Superseded-by | Safe-to-remove-when |
|------|-----------|----------|---------------|---------------------|
| `opencontext_core.adapters` package-level access (`__getattr__`) | `adapters/__init__.py:35` | already-deprecated (warns) | harness + sampling gateway | 2.0. **Submodule classes stay live** (used by `verify`/`doctor` health checks in `verification.py`) — only the public package surface is removed. |

## 7. Workflow pack signing (dead, superseded)

| Item | Path:line | Category | Superseded-by | Safe-to-remove-when |
|------|-----------|----------|---------------|---------------------|
| `workflow_packs/signing.py` (`WorkflowPackSigner`, `WorkflowPackVerifier`, `workflow_pack_manifest_hash`) | `workflow_packs/signing.py:3` | dead | `marketplace.signing` | 2.0 (no runtime caller; only its own tests construct it — comment-only, no `__init__` to warn from without structural change) |

## 8. Memory (legacy direct-write branch — documented, NOT code-marked)

`MemoryHarvester` (`memory/harvester.py:96`) is the **live** entry point. Its
legacy *direct-write branch* (when no `MemoryHarness` is injected) is the default
while `runtime.memory_v2_enabled` is `False`. The class itself is not deprecated —
it delegates to `MemoryHarness` when v2 is enabled — so it is left unmarked to
avoid mistagging live code. Removal target: the direct-write branch can go once
`memory_v2_enabled` is the default and the legacy path is removed (PR-009).

---

## Verified NOT dead / NOT marked (don't re-chase)

- **`OpenContextRuntime`** (`runtime/__init__.py:259`) — ledger lists it
  (`adapted`, `session_wrapper`, milestone-B) but it is the **live primary facade**
  with 40+ callers (CLI `_runtime()`, harness, onboarding, evaluation). The old
  flat `runtime.py` was already folded into `runtime/__init__.py`; there is no dead
  remnant. Not marked.
- **`HarnessRunner`** (`harness/runner.py`) — the **chosen** execution spine of the
  two-spine convergence; stays. Only its legacy `_WORKFLOW_TRACK_ALIASES` resolution
  is marked (§2).
- **`MemoryHarvester`** — live delegator (see §8).
- **Adapter submodule classes** — live (health checks); see §6.

## Already removed by earlier cleanup (resolved — confirmed gone)

- `packages/opencontext_providers/` (orphaned 2nd providers package) — deleted; not
  in root `pyproject` members.
- `context/observability.py` (`OtelExporter`, `ContextDashboard`, …) — deleted.
- `safety/proxy.py` (`SimpleProxyServer`, `ProxyPolicy`, proxy `ContextFirewall`) — deleted.
- `workflow_packs._packs()` — no longer exists.
